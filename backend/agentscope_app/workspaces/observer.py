"""Independent bounded observations. Cached green is never authority."""
import copy
import json
import os
import datetime
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from ..broker_client import call as broker
from .. import db

INTERVAL = 3
TIMEOUT = 2
TTL = 8


def iso(timestamp):
    return datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc).isoformat()


# Pauses are gates on a running phase; only these phases can own an active web binding.
ACTIVE_WEB_PHASES = {'running', 'recovering', 'generating'}


def managed_catalog():
    """Recoverable archives do not constitute active execution connections."""
    with db.connect() as con:
        closed = {row['task_id'] for row in con.execute("SELECT DISTINCT task_id FROM managed_events WHERE kind='closed'")}
        rows = con.execute("SELECT m.task_id,m.state_json,t.ended_at,t.workspace,t.dsh_profile FROM managed_tasks m JOIN tasks t ON t.id=m.task_id").fetchall()
    active, failed_candidates = {}, {}
    for row in rows:
        state = json.loads(row['state_json'])
        task_id = row['task_id']
        if row['ended_at'] or task_id in closed or row['dsh_profile'] != 'web':
            continue
        item = {'state': state, 'workspace': row['workspace']}
        if state.get('phase') in ACTIVE_WEB_PHASES:
            active[task_id] = item
        elif state.get('phase') == 'failed':
            # Only a new live Broker observation can admit a failed-state race.
            failed_candidates[task_id] = item
    return active, failed_candidates


def retain_managed_row(row, key, active, failed_candidates):
    if row.get('kind') != 'managed':
        return True
    task_id = row.get('task_id', key.removeprefix('managed:'))
    if task_id in active:
        return True
    return (task_id in failed_candidates and row.get('_live_confirmed_failed') is True
            and row.get('connected') is True and time.monotonic()-row['_monotonic'] < TTL)


class Observer:
    def __init__(self):
        self.lock = threading.RLock()
        self.collect_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.rows = {}
        self.sequence = 0

    def start(self):
        if os.getenv('AGENTSCOPE_INSTANCE_WORKER', '1') == '0':
            return
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.run, name='dsh-instance-observer', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(3)

    def run(self):
        while not self.stop_event.is_set():
            began = time.monotonic()
            try:
                self.collect()
            except Exception:
                self.invalidate()
            self.stop_event.wait(max(.05, INTERVAL-(time.monotonic()-began)))

    def invalidate(self):
        with self.lock:
            for row in self.rows.values():
                row.update(status='unknown', connected=False, available=False, error='控制接口不可达，实例当前状态未知')

    def collect(self, selected=None):
        # A manual check always performs a new broker roundtrip, never returns an
        # in-flight/background result. Serial generations prevent old overwrite.
        with self.collect_lock:
            active, failed_candidates = managed_catalog()
            with self.lock:
                self.rows = {key: row for key, row in self.rows.items()
                             if retain_managed_row(row, key, active, failed_candidates)}
            try:
                inventory = broker({'action': 'dsh-instance-inventory'}, timeout=TIMEOUT)['instances']
            except Exception:
                self.invalidate()
                with self.lock:
                    for task_id, item in active.items():
                        state = item['state']
                        instance_id = 'managed:'+task_id
                        if instance_id not in self.rows and (state.get('session_id') or state.get('binding')):
                            observed = time.time()
                            self.rows[instance_id] = {
                                'id': instance_id, 'instance_id': instance_id, 'kind': 'managed',
                                'name': '受管 DSH · '+task_id, 'task_id': task_id,
                                'roots': [item['workspace']], 'status': 'unknown',
                                'connected': False, 'available': False,
                                'error': '控制接口不可达，实例当前状态未知',
                                'observed_at': iso(observed), 'expires_at': iso(observed+TTL),
                                '_observed': observed, '_monotonic': time.monotonic()}
                if selected:
                    raise ValueError('实例清单不可用，请重试')
                return
            inventory = [row for row in inventory if row.get('kind') != 'managed' or row.get('task_id') in active or row.get('task_id') in failed_candidates]
            present = {row['id'] for row in inventory}
            # Keep recheck entries only for active web bindings. Failed or
            # headless archives must never synthesize a managed web instance.
            for task_id, item in active.items():
                state = item['state']
                instance_id = 'managed:'+task_id
                if instance_id not in present and (state.get('session_id') or state.get('binding')):
                    inventory.append({'id': instance_id, 'instance_id': instance_id, 'kind': 'managed',
                                      'name': '受管 DSH · '+task_id, 'task_id': task_id,
                                      'roots': [item['workspace']]})
            if selected and selected not in {r['id'] for r in inventory}:
                with self.lock:
                    if selected in self.rows:
                        self.rows[selected].update(status='offline', connected=False, available=False, error='实例登记已移除')
                raise ValueError('此执行实例不存在')
            sessions = {task_id: item['state'].get('session_id') for task_id, item in {**active, **failed_candidates}.items()}
            pool = ThreadPoolExecutor(max_workers=max(1, min(24, len(inventory))))
            pending = {}
            for row in inventory:
                if selected and row['id'] != selected:
                    continue
                message = {'action': 'dsh-instance-observe', 'instance_id': row['id'],
                           'session_id': sessions.get(row.get('task_id'))}
                pending[pool.submit(broker, message, timeout=TIMEOUT)] = row
            from concurrent.futures import wait
            done, unfinished = wait(pending, timeout=TIMEOUT+.05)
            results = []
            for future, row in pending.items():
                observed = time.time()
                value = {'status': 'unknown', 'connected': False, 'available': False,
                         'error': '控制接口未在期限内返回，实例当前状态未知'}
                if future in done:
                    try:
                        value = future.result()
                    except (OSError, TimeoutError):
                        pass
                    except Exception:
                        value.update(status='unresponsive', error='实例本次独立检查未通过')
                live_failed = row.get('kind') == 'managed' and row.get('task_id') in failed_candidates
                if live_failed and value.get('connected') is not True:
                    continue
                self.sequence += 1
                results.append({**row, **value, 'check_sequence': self.sequence,
                                'observed_at': iso(observed), 'expires_at': iso(observed+TTL),
                                '_observed': observed, '_monotonic': time.monotonic(), '_live_confirmed_failed': live_failed})
            pool.shutdown(wait=False, cancel_futures=True)
            with self.lock:
                if not selected:
                    self.rows = {row['id']: row for row in results}
                else:
                    self.rows.pop(selected, None)
                    self.rows.update({row['id']: row for row in results})
            from .registry import sync_observation
            for row in results:
                if row.get('connected'):
                    sync_observation(row)

    def snapshot(self):
        now = time.monotonic()
        active, failed_candidates = managed_catalog()
        with self.lock:
            self.rows = {key: row for key, row in self.rows.items()
                         if retain_managed_row(row, key, active, failed_candidates)}
            rows = copy.deepcopy(list(self.rows.values()))
        for row in rows:
            age = now-row.pop('_monotonic')
            row.pop('_observed', None)
            row.pop('_live_confirmed_failed', None)
            row['evidence_age_seconds'] = round(age, 3)
            if age >= TTL:
                row.update(status='stale', connected=False, available=False, error='连接证据已过期，等待独立检查')
            row.pop('socket', None)
            row.pop('service', None)
            row.pop('uid', None)
            row.setdefault('pid', None)
            row.setdefault('start_ticks', None)
            row.setdefault('generation', None)
            row.setdefault('capabilities', [])
            row.setdefault('error', '')
            row.setdefault('running_tasks', 1 if row['kind'] == 'managed' and row.get('connected') else 0)
            row['connection_basis'] = '本机进程身份、启动时刻及当前代桥接握手；配置有效不构成连接'
        return rows

    def require(self, instance_id):
        row = next((r for r in self.snapshot() if r['id'] == instance_id), None)
        if not row or not row.get('connected'):
            raise ValueError('执行实例未接入或连接证据已过期，请检查连接')
        return row


observer = Observer()
