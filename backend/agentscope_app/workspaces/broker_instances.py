"""Privileged, fixed-configuration DSH observations. No Agent activation."""
import hashlib
import json
import os
import re
import secrets
import socket
import stat
import struct
import subprocess
from pathlib import Path

CONFIG = Path('/etc/agentscope/dsh-instances.json')
PROTOCOL = 1
ID = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$')


def registrations():
    if not CONFIG.exists():
        return [{'id': 'native-dsh', 'name': '原生 DSH', 'service': os.getenv('AGENTSCOPE_NATIVE_DSH_SERVICE', 'dsh.service'),
                 'socket': '/run/agentscope-dsh/instance.sock', 'roots': []}]
    info = CONFIG.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise PermissionError('DSH instance configuration must be root-owned and not writable by others')
    data = json.loads(CONFIG.read_text())
    result = []
    for row in data['instances']:
        if row['id'] == 'dsh' or not ID.fullmatch(row['id']) or not re.fullmatch(r'[a-zA-Z0-9_.@-]+\.service', row['service']):
            raise ValueError('Invalid registered instance')
        endpoint = Path(row['socket'])
        if not endpoint.is_absolute() or endpoint.parent != Path('/run/agentscope-dsh'):
            raise ValueError('Bridge socket must be directly under /run/agentscope-dsh')
        roots = [str(Path(p).resolve(strict=True)) for p in row.get('roots', [])]
        if any(not Path(p).is_dir() or p == '/' for p in roots):
            raise ValueError('Invalid operator workspace root')
        result.append({**row, 'roots': roots})
    if len(result) > 20 or len({r['id'] for r in result}) != len(result):
        raise ValueError('Invalid instance registration count or duplicate identities')
    return result


def process_identity(pid):
    raw = (Path('/proc') / str(pid) / 'stat').read_text()
    fields = raw[raw.rfind(')')+2:].split()
    uid = (Path('/proc') / str(pid)).stat().st_uid
    return {'pid': int(pid), 'uid': uid, 'start_ticks': fields[19]}


def service_identity(row):
    output = subprocess.run(['systemctl', 'show', row['service'], '--property=MainPID', '--value'],
                            capture_output=True, text=True, timeout=.5, check=True)
    pid = int(output.stdout.strip() or '0')
    return process_identity(pid) if pid > 0 else None


def generation(instance_id, identity):
    return hashlib.sha256((instance_id+':'+str(identity['pid'])+':'+identity['start_ticks']).encode()).hexdigest()[:24]


def checked_path(path, roots, allow_root=True):
    target = Path(path)
    resolved = target.resolve(strict=True)
    if str(target) != str(resolved) or not resolved.is_dir():
        raise ValueError('Directory must be an existing canonical directory')
    if not any((allow_root and resolved == Path(root)) or Path(root) in resolved.parents for root in roots):
        raise ValueError('Directory outside operator roots')
    return str(resolved)


def bridge_call(row, identity, operation='observe', path=None):
    nonce = secrets.token_hex(24)
    request = {'version': PROTOCOL, 'nonce': nonce, 'instance_id': row['id'],
               'generation': generation(row['id'], identity), 'operation': operation}
    if path is not None:
        request['path'] = checked_path(path, row['roots'])
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        channel.settimeout(1.1)
        channel.connect(row['socket'])
        pid, uid, _ = struct.unpack('3i', channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if (pid, uid) != (identity['pid'], identity['uid']):
            raise PermissionError('Bridge peer does not match registered service process')
        channel.sendall(json.dumps(request).encode()+b'\n')
        raw = b''
        while not raw.endswith(b'\n'):
            chunk = channel.recv(65536)
            if not chunk:
                raise RuntimeError('Bridge closed before responding')
            raw += chunk
            if len(raw) > 1_000_000:
                raise ValueError('Bridge response too large')
    reply = json.loads(raw)
    if any(reply.get(k) != request[k] for k in ('version', 'nonce', 'instance_id', 'generation')):
        raise PermissionError('Bridge handshake mismatch')
    if process_identity(pid) != identity or service_identity(row) != identity:
        raise PermissionError('DSH service generation changed during observation')
    if not reply.get('ok'):
        raise RuntimeError('Native DSH operation unavailable')
    return reply['result']


def live_managed_record(record):
    """Popen liveness plus current /proc identity, never a remembered PID alone."""
    watch = record.get('watch')
    if record.get('scope_mode') != 'managed-web' or watch is None or watch.poll() is not None:
        return False
    try:
        identity = process_identity(watch.pid)
    except (OSError, ValueError):
        return False
    return identity['pid'] == watch.pid


def inventory(tasks, lock):
    native = [{**r, 'kind': 'native', 'instance_id': r['id']} for r in registrations()]
    with lock:
        records = list(tasks.items())
    managed = [{'id': 'managed:'+k, 'instance_id': 'managed:'+k, 'name': '受管 DSH · '+k,
                'kind': 'managed', 'task_id': k, 'roots': [v['workspace']]}
               for k, v in records if live_managed_record(v)]
    return {'instances': native+managed}


def observe(instance_id, tasks, lock, status_fn, native_fn, session_id=None):
    if instance_id.startswith('managed:'):
        task_id = instance_id.split(':', 1)[1]
        with lock:
            record = tasks.get(task_id)
            if not record or record.get('scope_mode') != 'managed-web':
                return {'status': 'offline', 'connected': False, 'available': False}
            record = dict(record)
        execution = status_fn(task_id)
        pid = (execution.get('executor') or {}).get('pid')
        if execution.get('status') != 'running' or not pid:
            return {'status': 'offline', 'connected': False, 'available': False}
        try:
            identity = process_identity(pid)
        except (OSError, ValueError):
            return {'status': 'offline', 'connected': False, 'available': False}
        state = native_fn({'task_id': task_id, 'operation': 'observe', 'session_id': session_id})
        if not session_id or state.get('session_id') != session_id:
            raise RuntimeError('Managed native session binding changed')
        if process_identity(pid) != identity:
            raise RuntimeError('Managed process generation changed')
        return {**identity, 'generation': generation(instance_id, identity), 'status': 'connected',
                'connected': True, 'available': True, 'session_id': state.get('session_id'),
                'workspaces': [{'workspaceId': task_id, 'path': record['workspace'], 'title': '任务工作区',
                                'sessionIds': [session_id] if session_id else []}],
                'roots': [record['workspace']], 'capabilities': ['workspace_read', 'managed_execution']}
    row = next((r for r in registrations() if r['id'] == instance_id), None)
    if row is None:
        raise ValueError('Unknown registered DSH instance')
    identity = service_identity(row)
    if not identity:
        return {'status': 'offline', 'connected': False, 'available': False, 'roots': row['roots']}
    result = {**identity, 'generation': generation(instance_id, identity), 'available': True, 'roots': row['roots']}
    try:
        native = bridge_call(row, identity)
        workspaces = []
        for item in native.get('workspaces', []):
            try:
                checked_path(item['path'], row['roots'])
                workspaces.append(item)
            except (OSError, ValueError):
                continue
        return {**result, 'status': 'connected', 'connected': True, 'workspaces': workspaces,
                'sync_revision': native.get('sync_revision'), 'capabilities': ['workspace_read', 'workspace_create', 'directory_list']}
    except ConnectionRefusedError:
        return {**result, 'status': 'offline', 'connected': False, 'available': False, 'error': 'DSH 桥接未监听，执行实例当前不可接入'}
    except FileNotFoundError:
        return {**result, 'status': 'running_unattached', 'connected': False, 'error': 'DSH 正在运行，尚未安装实例桥接'}
    except (OSError, RuntimeError, ValueError, PermissionError):
        return {**result, 'status': 'unresponsive', 'connected': False, 'error': 'DSH 桥接未通过本次独立检查'}


def workspace_operation(message):
    row = next((r for r in registrations() if r['id'] == message.get('instance_id')), None)
    if row is None:
        raise ValueError('Only registered native instances support workspace operations')
    identity = service_identity(row)
    if not identity or generation(row['id'], identity) != message.get('generation'):
        raise ValueError('DSH generation changed; check connection again')
    operation = message.get('operation')
    if operation not in ('workspace-create', 'directory-list'):
        raise ValueError('Native operation is not allowed')
    path = message.get('path') or (row['roots'][0] if row['roots'] else '')
    result = bridge_call(row, identity, operation, path)
    if operation == 'directory-list':
        # Native breadcrumbs can extend above the allowlist. Never expose them.
        result['crumbs'] = [r for r in result.get('crumbs', []) if any(Path(r['path']) == root or root in Path(r['path']).parents for root in map(Path, row['roots']))]
        entries = []
        for item in result.get('entries', []):
            try:
                checked_path(item['path'], row['roots'])
                entries.append(item)
            except (OSError, ValueError):
                continue
        result['entries'] = entries
        result['home'] = next((root for root in row['roots'] if Path(root) == Path(path) or Path(root) in Path(path).parents), '')
    return result
