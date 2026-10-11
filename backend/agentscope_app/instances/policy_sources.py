"""Read-only executable facts for customer policy drafting; never launch or apply."""
import os
import json
import stat
import time
import re
from pathlib import Path

IDENTITY = ('generation', 'pid', 'start_ticks', 'domain_id', 'host_id', 'boot_id')


def process_executable(pid, start_ticks, boot_id):
    # Only an already admitted runtime PID reaches this reader. No argv, env or file contents.
    if type(pid) is not int or pid <= 0:
        raise ValueError('当前 Agent 的运行进程无效，请刷新连接')
    proc = Path('/proc') / str(pid)
    try:
        if Path('/proc/sys/kernel/random/boot_id').read_text().strip() != boot_id:
            raise ValueError('当前 Agent 不属于本机运行环境，请刷新连接')
        before = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]
        executable = os.readlink(proc / 'exe')
        after_executable = os.readlink(proc / 'exe')
        after = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]
    except PermissionError:
        raise
    except (OSError, IndexError):
        raise ValueError('无法读取当前 Agent 的执行程序，请连接并核验后重试') from None
    if before != str(start_ticks) or after != before or executable != after_executable:
        raise ValueError('当前 Agent 的运行进程已变化，请刷新连接')
    basename = executable.rsplit('/', 1)[-1]
    if not executable.startswith('/') or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,15}', basename):
        raise ValueError('当前执行程序无法准确匹配，请核验 Agent 运行环境')
    return executable


def source_for(row):
    runtime = row.get('runtime') or {}
    if row.get('mode') != 'controlled' or not row.get('connected') or not runtime.get('verified'):
        raise ValueError('请连接并核验当前 Agent 后再读取启动来源')
    if any(not runtime.get(k) or row.get(k) != runtime.get(k) for k in IDENTITY):
        raise ValueError('当前 Agent 的运行身份已变化，请刷新连接')
    try:
        executable = process_executable(runtime['pid'], runtime['start_ticks'], runtime['boot_id'])
    except PermissionError:
        executable = cached_executable(row)
    return {'pattern': '**/' + executable.rsplit('/', 1)[-1],
            'entry': runtime.get('executable', ''), 'executable': executable,
            'basis': 'verified-process-executable'}


def source_status(row):
    try:
        source = source_for(row)
        runtime = row['runtime']
        return {'ready': True, 'instance_id': row['id'], **source,
                **{k: runtime[k] for k in IDENTITY}}
    except ValueError as e:
        return {'ready': False, 'instance_id': row['id'], 'message': str(e)}


def source_context(scope, rows):
    selected = [r for r in rows if r.get('mode') == 'controlled' and (scope == 'system' or r['id'] == scope)]
    sources, unavailable = [], []
    for row in selected:
        fact = source_status(row)
        name = {'dsh': 'DeepSeek Harness', 'hermes': 'Hermes'}.get(row.get('agent_type'), row.get('name') or 'Agent')
        (sources if fact['ready'] else unavailable).append({**fact, 'id': row['id'], 'name': name})
    return {'scope_id': scope, 'ready': bool(sources) and not unavailable,
            'sources': sources, 'unavailable': unavailable,
            'message': '请先连接并核验受控 Agent' if not selected else '部分 Agent 尚未连接或运行身份待核验' if unavailable else ''}


CACHE = Path('/run/agentscope-scope-demo/policy-source-facts.json')


def cached_fact(snapshot, row, now):
    runtime = row['runtime']
    age = now - snapshot.get('observed_monotonic', -100)
    if not 0 <= age < 8 or snapshot.get('boot_id') != runtime['boot_id']:
        raise ValueError('当前运行来源已过期，请等待连接重新核验')
    fact = snapshot.get('sources', {}).get(row['id']) or {}
    if any(fact.get(k) != runtime[k] for k in IDENTITY):
        raise ValueError('当前运行来源与 Agent 身份不一致，请刷新连接')
    executable = fact.get('executable', '')
    if not executable.startswith('/') or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,15}', executable.rsplit('/',1)[-1]):
        raise ValueError('当前 Agent 的执行程序尚未核验')
    return executable


def cached_executable(row):
    try:
        # Open without symlink following; the API cannot write the root-owned parent.
        fd = os.open(CACHE, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or info.st_size > 1000000:
                raise ValueError('运行来源观察记录尚未核验')
            snapshot = json.load(stream)
        return cached_fact(snapshot, row, time.monotonic())
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        raise ValueError('暂时无法读取运行来源，请等待连接重新核验') from None
