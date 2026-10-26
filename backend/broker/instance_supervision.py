"""Broker-owned admission and durable metadata; the console is not a heartbeat.

This module does not execute tools or approve policy. Its authority is the frozen
launch policy and a fresh proof supplied by the root Broker, never Agent claims.
"""
import json
import os
import sqlite3
import stat
import threading
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA = 'broker-admission-v1'
MAX_EVENTS = 4096
MAX_CALLS = 65536  # Completed identities remain replay tombstones for this generation.
FIELDS = ('generation', 'session_id', 'call_id', 'tool')


class Admission:
    def __init__(self, directory, generation, policy, policy_hash, *, owner=0, tagger=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.owner = owner
        self.generation = generation
        self.policy = json.loads(json.dumps(policy))
        self.policy_hash = policy_hash
        self.tagger = tagger
        self.lock = threading.RLock()
        self.last_verified = 0.0
        self.gate = False
        self.reason = '启动保护尚未核验'
        self.database = self.directory / ('admission-' + generation + '.sqlite3')
        self._safe(self.directory, directory=True)
        if self.database.exists():
            raise ValueError('An admission generation cannot be resurrected')
        descriptor = os.open(self.database, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        with self.connect() as con:
            con.executescript('''
                CREATE TABLE events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL, payload TEXT NOT NULL, created_at REAL NOT NULL);
                CREATE TABLE calls(call_id TEXT PRIMARY KEY, identity TEXT NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0, succeeded INTEGER, result_sequence INTEGER,
                    binding_json TEXT NOT NULL DEFAULT '{}');
                CREATE TABLE state(singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    gate INTEGER NOT NULL, reason TEXT NOT NULL, changed_at REAL NOT NULL);
            ''')
            con.execute('INSERT INTO state VALUES(1,0,?,?)', (self.reason, time.time()))

    def _safe(self, path, *, directory=False):
        info = path.lstat()
        expected = stat.S_ISDIR if directory else stat.S_ISREG
        if path.is_symlink() or not expected(info.st_mode) or info.st_uid != self.owner or info.st_mode & 0o077:
            raise ValueError('Unsafe Broker admission storage')

    @contextmanager
    def connect(self):
        self._safe(self.directory, directory=True)
        self._safe(self.database)
        con = sqlite3.connect(self.database, timeout=1)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def verified(self):
        with self.lock:
            self.last_verified = time.monotonic()

    def fresh(self):
        return self.last_verified > 0 and time.monotonic() - self.last_verified < 3

    def set_gate(self, opened, reason):
        with self.lock:
            if opened and not self.fresh():
                raise ValueError('Execution protection is not freshly verified')
            reason = str(reason)[:200]
            if not opened:
                self.gate = False
                self.reason = reason
            with self.connect() as con:
                con.execute('UPDATE state SET gate=?,reason=?,changed_at=? WHERE singleton=1',
                            (int(opened), reason, time.time()))
            self.gate = bool(opened)
            self.reason = reason
            return self.status()

    def identity(self, body):
        if not isinstance(body, dict) or set(body) - {*FIELDS, 'succeeded', 'pid'}:
            raise ValueError('Invalid tool event fields')
        if self.tagger and (type(body.get('pid')) is not int or body['pid'] <= 0):
            raise ValueError('Native process identity is required')
        for key, maximum in (('generation', 32), ('session_id', 200), ('call_id', 200), ('tool', 100)):
            value = body.get(key)
            if not isinstance(value, str) or not 0 < len(value) <= maximum:
                raise ValueError('Invalid tool event identity')
        if body['generation'] != self.generation:
            raise ValueError('Tool generation changed')
        return json.dumps({key: body[key] for key in (*FIELDS,*(['pid'] if self.tagger else []))}, sort_keys=True, separators=(',', ':'))

    def lease(self, body):
        if 'succeeded' in body:
            raise ValueError('A lease cannot contain a result')
        identity = self.identity(body)
        with self.lock, self.connect() as con:
            if not self.gate or not self.fresh():
                return {'allowed': False, 'reason': self.reason if not self.gate else '执行保护核验已过期'}
            rule = next((r for r in self.policy.get('rules', []) if r['action'] == 'tool'
                         and r['target'] == body['tool'] and r['effect'] != 'allow'), None)
            if rule:
                return {'allowed': False, 'reason': '已批准策略未授权此工具'}
            old = con.execute('SELECT * FROM calls WHERE call_id=?', (body['call_id'],)).fetchone()
            if old:
                if old['identity'] != identity or old['completed']:
                    return {'allowed': False, 'reason': '工具调用身份已变化或调用已经完成'}
                return {'allowed': True, 'idempotent': True, **json.loads(old['binding_json'])}
            events = con.execute('SELECT COUNT(*) FROM events').fetchone()[0]
            outstanding = con.execute('SELECT COUNT(*) FROM calls WHERE completed=0').fetchone()[0]
            if self.tagger and outstanding:
                return {'allowed': False, 'reason': '同一原生执行进程已有工具运行，请串行调用'}
            if con.execute('SELECT COUNT(*) FROM calls').fetchone()[0] >= MAX_CALLS:
                return {'allowed': False, 'reason': '本次运行记录已达到容量，请确认后重新启动实例'}
            # Reserve completion capacity before admitting any action.
            if events + outstanding + 2 > MAX_EVENTS:
                return {'allowed': False, 'reason': '执行记录等待同步，请稍后重试'}
            try:binding = self.tagger('start',body) if self.tagger else {}
            except (OSError,ValueError,RuntimeError):
                reason='原生执行身份或调用标记未通过核验，工具未执行'
                con.execute('INSERT INTO events(kind,payload,created_at) VALUES(?,?,?)',
                    ('tool_denied',json.dumps({**json.loads(identity),'reason':reason}),time.time()))
                return {'allowed':False,'reason':reason}
            con.execute('INSERT INTO calls(call_id,identity,binding_json) VALUES(?,?,?)', (body['call_id'], identity,json.dumps(binding)))
            con.execute('INSERT INTO events(kind,payload,created_at) VALUES(?,?,?)',
                        ('tool_start', json.dumps({**json.loads(identity),**binding}), time.time()))
            return {'allowed': True, 'supervision': SCHEMA, **binding}

    def result(self, body):
        identity = self.identity(body)
        if type(body.get('succeeded')) is not bool:
            raise ValueError('Invalid tool result')
        with self.lock, self.connect() as con:
            old = con.execute('SELECT * FROM calls WHERE call_id=?', (body['call_id'],)).fetchone()
            if not old or old['identity'] != identity:
                raise ValueError('Result has no matching admitted call')
            if old['completed']:
                if bool(old['succeeded']) != body['succeeded']:
                    raise ValueError('Completed result changed')
                return {'ok': True, 'idempotent': True}
            payload = json.loads(identity)
            if self.tagger:self.tagger('end',body)
            payload.update(json.loads(old['binding_json']))
            payload['succeeded'] = body['succeeded']
            cursor = con.execute('INSERT INTO events(kind,payload,created_at) VALUES(?,?,?)',
                                 ('tool_result', json.dumps(payload), time.time()))
            con.execute('UPDATE calls SET completed=1,succeeded=?,result_sequence=? WHERE call_id=?',
                        (int(body['succeeded']), cursor.lastrowid, body['call_id']))
            return {'ok': True, 'queued': True, 'sequence': cursor.lastrowid}

    def events(self, after=0):
        if type(after) is not int or after < 0:
            raise ValueError('Invalid event cursor')
        with self.lock, self.connect() as con:
            return [{'sequence': r['sequence'], 'kind': r['kind'], 'payload': json.loads(r['payload']),
                     'created_at': r['created_at']} for r in con.execute(
                'SELECT * FROM events WHERE sequence>? ORDER BY sequence LIMIT 100', (after,))]

    def observation(self,body):
        if set(body)-{*FIELDS,'pid','kind'} or body.get('kind')!='turn_end':raise ValueError('Invalid native lifecycle event')
        payload={k:v for k,v in body.items() if k!='kind'}
        identity=self.identity(payload)
        with self.lock,self.connect() as con:
            if con.execute('SELECT COUNT(*) FROM events').fetchone()[0]>=MAX_EVENTS:raise ValueError('Lifecycle queue is full')
            if not con.execute("SELECT 1 FROM events WHERE kind='turn_end' AND payload=?",(identity,)).fetchone():
                con.execute('INSERT INTO events(kind,payload,created_at) VALUES(?,?,?)',('turn_end',identity,time.time()))
        return {'ok':True}

    def acknowledge(self, sequence):
        if type(sequence) is not int or sequence < 0:
            raise ValueError('Invalid acknowledgement')
        with self.lock, self.connect() as con:
            con.execute('DELETE FROM events WHERE sequence<=?', (sequence,))
            # ACK frees the outbound queue, never the replay protection identity.
        return {'ok': True}

    def status(self):
        with self.lock, self.connect() as con:
            state = dict(con.execute('SELECT * FROM state WHERE singleton=1').fetchone())
            count = con.execute('SELECT COUNT(*) FROM events').fetchone()[0]
            outstanding = con.execute('SELECT COUNT(*) FROM calls WHERE completed=0').fetchone()[0]
        return {'schema': SCHEMA, 'generation': self.generation, 'policy_hash': self.policy_hash,
                'gate': 'open' if self.gate else 'closed', 'protection_fresh': self.fresh(),
                'reason': self.reason, 'changed_at': state['changed_at'], 'pending_events': count,
                'outstanding_calls': outstanding, 'console_required_for_execution': False}
