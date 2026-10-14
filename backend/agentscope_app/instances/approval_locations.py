"""Read-only customer locations; never infer session ownership from names or PIDs."""
import json
from .. import db
from ..history.pipeline import digest
from . import controller

PRODUCTS = {'dsh': 'DeepSeek Harness', 'hermes': 'Hermes', 'codex': 'Codex',
            'hermes-desktop': 'Hermes Desktop'}


def product(row):
    return PRODUCTS.get(row.get('agent_type'), row.get('name') or 'Agent')


def positive_pid(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


class Locations:
    def __init__(self):
        self.agents = {r['id']: r for r in controller.listing()['instances']}
        self.origins = {}
        with db.connect() as con:
            self.sessions = {(r['instance_id'], r['session_id']): json.loads(r['metadata_json'])
                             for r in con.execute('SELECT instance_id,session_id,metadata_json FROM instance_session_cache')}
            for r in con.execute('SELECT instance_id,session_id,name FROM instance_session_display_names'):
                if (r['instance_id'],r['session_id']) in self.sessions:self.sessions[(r['instance_id'],r['session_id'])]['name']=r['name']

    def target(self, frozen):
        live = self.agents.get(frozen['id'], {})
        connected = bool(live.get('connected') and live.get('verified'))
        return {'id': frozen['id'], 'name': product(live or frozen),
                'agent_type': (live or frozen).get('agent_type'),
                'pid': positive_pid(live.get('pid')) if connected else None,
                'process_state': 'running' if connected else 'offline' if live.get('gate') == 'closed' else 'unverified',
                'submitted_pid': positive_pid(frozen.get('pid')) if frozen.get('active') else None,
                'active': bool(live.get('active'))}

    def origin(self, scope, binding):
        key = (scope, binding.get('artifact_id'), binding.get('context_hash'))
        if key in self.origins:
            return self.origins[key]
        self.origins[key] = None
        # Historical location must survive environment drift; do not call the live
        # candidate revalidation path or guess an association for manual imports.
        from ..history.registry import load_statement
        with db.connect() as con:
            artifact = con.execute('SELECT statement_version_id FROM history_artifacts WHERE id=?', (key[1],)).fetchone()
        if not artifact:
            return None
        try:
            ctx = load_statement(artifact['statement_version_id']).resolved_context
            env = ctx.get('environment_binding', {})
            values = env.get('values', {})
            sid = ctx.get('session_id')
            if (ctx.get('policy_scope')=='agent' and sid is None and ctx.get('instance_id')==scope
                    and values.get('instance_id')==scope and env.get('hash')==key[2] and digest(values)==key[2]):
                self.origins[key]={'baseline':True}
                return self.origins[key]
            if (ctx.get('kind') != 'agent' or ctx.get('instance_id') != scope or not isinstance(sid, str) or not sid
                    or values.get('instance_id') != scope or values.get('session_id') != sid
                    or env.get('hash') != key[2] or digest(values) != key[2]):
                return None
        except (ValueError, TypeError, KeyError):
            return None
        cached = self.sessions.get((scope, sid))
        origin = {'instance_id': scope, 'session_id': sid,
                  'name': cached.get('name') or '未命名会话' if cached else '会话记录暂不可用',
                  'available': cached is not None,
                  'generation_pid': positive_pid(values.get('runtime', {}).get('pid'))}
        self.origins[key] = origin
        return origin

    def project(self, p, visible_targets):
        targets = [self.target(t) for t in visible_targets]
        origins = {}
        baseline=False
        for doc in p['documents']:
            binding = doc.get('generation_binding')
            origin = self.origin(p['scope_id'], binding) if binding else None
            if origin and origin.get('baseline'):
                baseline=True
            elif origin:
                origins[(origin['instance_id'], origin['session_id'])] = origin
        return {'agents': targets, 'origin_sessions': list(origins.values()),
                'origin_state': 'linked' if origins else 'agent_baseline' if baseline else 'unavailable' if any(d.get('generation_binding') for d in p['documents']) else 'unrecorded'}
