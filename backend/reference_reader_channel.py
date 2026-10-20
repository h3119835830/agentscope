"""Private inherited transport for the fixed, unprivileged reference reader.

No listener, shell, caller-selected executable, identity change or policy write.
The privileged service launcher creates the channel before dropping API identity.
"""
import ctypes
import json
import os
from pathlib import Path
import resource
import socket
import struct
import subprocess
import sys
import threading
import time

FD_ENV = 'AGENTSCOPE_REFERENCE_READER_FD'
MAX_REQUEST = 30000
MAX_RESPONSE = 1600000
WORKER = Path(__file__).with_name('reference_file_reader.py')


class ReaderUnavailable(ValueError):
    def __init__(self):
        super().__init__('工作区资料读取服务不可用，请管理员检查读取进程；不是场景文件的策略拒绝')


def harden():
    """Do not expose read buffers to same-UID processes or gain exec privileges."""
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) or libc.prctl(4, 0, 0, 0, 0):
        raise OSError('reader isolation unavailable')


def receive(connection, maximum):
    def exact(size):
        data = bytearray()
        while len(data) < size:
            part = connection.recv(size - len(data))
            if not part:
                raise EOFError
            data.extend(part)
        return bytes(data)
    size = struct.unpack('!I', exact(4))[0]
    if not 0 < size <= maximum:
        raise ValueError('invalid frame')
    return json.loads(exact(size))


def send(connection, value, maximum):
    raw = json.dumps(value, ensure_ascii=False).encode()
    if not 0 < len(raw) <= maximum:
        raise ValueError('invalid frame')
    connection.sendall(struct.pack('!I', len(raw)) + raw)


def validate(payload):
    if not isinstance(payload, dict):
        raise ValueError('invalid request')
    operation = payload.get('operation', 'read')
    fields = {'operation', 'root', 'path', 'cursor'} if operation == 'list' else {'operation', 'root', 'paths', 'max_total_bytes'}
    if operation not in ('list', 'read') or set(payload) - fields:
        raise ValueError('invalid operation')
    root = payload.get('root')
    if not isinstance(root, str) or not root.startswith('/') or root == '/' or any(p in ('', '.', '..') for p in root.split('/')[1:]):
        raise ValueError('invalid root')
    # The control plane still validates instance ownership, policies and types.
    # The unchanged fd-anchored reader independently validates paths and bytes.


def serve(connection):
    harden()
    if os.geteuid() == 0 or os.getgroups():
        raise ValueError('reader must be unprivileged without supplementary groups')
    send(connection, {'uid': os.geteuid(), 'gid': os.getegid(), 'groups': os.getgroups()}, 1024)
    while True:
        try:
            request = receive(connection, MAX_REQUEST)
        except EOFError:
            return
        try:
            if set(request) != {'payload', 'timeout'} or type(request['timeout']) not in (int, float) or not 0 < request['timeout'] <= 5:
                raise ValueError('invalid request')
            validate(request['payload'])
            result = subprocess.run(
                [sys.executable, '-I', str(WORKER)],
                input=json.dumps(request['payload']), capture_output=True, text=True,
                timeout=request['timeout'], cwd='/', env={'LANG': 'C.UTF-8'},
                close_fds=True,
            )
            if result.returncode or len(result.stdout.encode()) > MAX_RESPONSE - 1024:
                response = {'error': 'read_denied'}
            else:
                response = {'result': json.loads(result.stdout)}
        except (ValueError, OSError, subprocess.TimeoutExpired):
            response = {'error': 'read_denied'}
        send(connection, response, MAX_RESPONSE)


class Client:
    def __init__(self, connection, identity):
        self.connection = connection
        self.identity = identity
        self.lock = threading.Lock()
        self.broken = False
        os.set_inheritable(connection.fileno(), False)

    def read(self, payload, uid, gid, timeout):
        if self.identity != {'uid': uid, 'gid': gid, 'groups': []} or uid == 0 or self.broken:
            raise ReaderUnavailable()
        validate(payload)
        deadline = time.monotonic() + timeout
        if not self.lock.acquire(timeout=max(0, timeout)):
            raise ReaderUnavailable()
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ReaderUnavailable()
            self.connection.settimeout(remaining)
            send(self.connection, {'payload': payload, 'timeout': min(5, remaining)}, MAX_REQUEST)
            response = receive(self.connection, MAX_RESPONSE)
            if not isinstance(response, dict) or set(response) not in ({'result'}, {'error'}):
                raise ValueError('invalid response')
        except (OSError, EOFError, ValueError, struct.error):
            # Never reuse a channel after an incomplete exchange.
            self.broken = True
            self.connection.close()
            raise ReaderUnavailable() from None
        finally:
            self.lock.release()
        if 'error' in response:
            raise ValueError('所选文件无读取权限、格式不支持、超过限额或读取期间发生变化')
        return response['result']


def inherited_client():
    descriptor = os.environ.pop(FD_ENV, None)
    if descriptor is None:
        return None
    try:
        connection = socket.socket(fileno=int(descriptor))
        connection.settimeout(3)
        if connection.family != socket.AF_UNIX or connection.type != socket.SOCK_STREAM:
            raise ValueError('invalid channel')
        identity = receive(connection, 1024)
        return Client(connection, identity)
    except (OSError, ValueError, EOFError):
        raise ReaderUnavailable() from None


def launch(python, uid, gid):
    """Only the trusted root launcher may establish the exact reader identity."""
    if os.geteuid() != 0 or uid <= 0 or gid <= 0:
        raise ReaderUnavailable()
    parent, child = socket.socketpair()
    try:
        process = subprocess.Popen(
            [python, '-I', str(Path(__file__).resolve()), str(child.fileno())],
            user=uid, group=gid, extra_groups=[], pass_fds=(child.fileno(),),
            cwd='/', env={'LANG': 'C.UTF-8'}, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        os.set_inheritable(parent.fileno(), True)
        return parent, process
    except BaseException:
        parent.close()
        raise
    finally:
        child.close()


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(2)
    with socket.socket(fileno=int(sys.argv[1])) as channel:
        serve(channel)
