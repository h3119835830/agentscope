#!/usr/bin/env python3
"""Fresh isolated 18188 session panel acceptance; never changes production Agents."""
import json
import argparse
import os
import socket
import time
import urllib.request
import uuid
from pathlib import Path
import system_policy_acceptance_service as service
import deploy_policy_semantics as production
from accept_policy_lifecycle import broker as original_broker

STATE = Path('/var/lib/assession-security-20261014')
SOURCE = Path('/opt/assession-security-20261014')
PORT = 18188
REPORT = STATE / 'session-panel-acceptance.json'


def configure():
    service.STATE = STATE; service.SOURCE = SOURCE; service.TASKS = Path('/ps14' + STATE.name.removeprefix('assession-security-20261014'))
    service.RUNTIME = Path('/run') / STATE.name; service.PORT = PORT
    original = service.environment
    def environment():
        env = original(); env['ACTPLANE_BPF_PIN_ROOT'] = '/sys/fs/bpf/' + STATE.name
        return env
    service.environment = environment


def api(path, body=None):
    req = urllib.request.Request(f'http://127.0.0.1:{PORT}' + path,
        data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.load(response)


def production_snapshot():
    return {'api': production.service(production.UNIT),
            'broker': production.service('agentscope-scope-demo-broker.service'),
            'authority': production.authority(), 'listeners': production.listeners()}


def identity(row):
    return {k: row.get(k) for k in ('id', 'pid', 'generation', 'policy_hash', 'domain_id', 'active')}


def broker(body):
    import accept_policy_lifecycle as lifecycle
    lifecycle.SOCKET = str(service.RUNTIME / 'broker.sock')
    return original_broker(body)


def probe(row):
    return broker({'action': 'agent-instance-dsl-probe', 'instance_id': row['id'],
                   'generation': row['generation'], 'effect': 'block'})['probe']


def approve(created):
    return api('/api/console/approvals/' + created['approval_id'] + '/approve',
        {'proposal_hash': created['proposal']['proposal_hash'], 'request_key': uuid.uuid4().hex})


def apply(created, receipt):
    return api('/api/console/approvals/' + created['approval_id'] + '/apply',
        {'proposal_hash': created['proposal']['proposal_hash'], 'approval_hash': receipt['approval_hash'],
         'request_key': uuid.uuid4().hex})


def main():
    global STATE, SOURCE, PORT, REPORT
    assert os.geteuid() == 0
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', default='')
    parser.add_argument('--port', type=int, default=18188)
    args = parser.parse_args()
    assert not args.batch or args.batch.isalnum() and len(args.batch) <= 12
    assert 18180 <= args.port <= 18299
    STATE = Path(str(STATE) + args.batch); SOURCE = Path(str(SOURCE) + args.batch)
    PORT = args.port; REPORT = STATE / 'session-panel-acceptance.json'
    configure()
    if STATE.exists():
        raise RuntimeError('The isolated run is immutable; choose a fresh owned profile')
    with socket.socket() as check:
        assert check.connect_ex(('127.0.0.1', PORT)) != 0
    before = production_snapshot()
    service.start('/var/lib/agentscope-scope-demo/bin/actplane.capabilities.json')
    report = {'production_before': before, 'checks': {}, 'scope': 'isolated-real-native-sessions'}
    try:
        resource = Path('/s/instance-resources/ssp14' + args.batch); assert not resource.exists()
        resource.mkdir(mode=0o755)
        for name in ('README.md', '.agentscope-dsl-block.txt', '.agentscope-dsl-notify.txt'):
            p = resource / name; p.write_text('Synthetic session panel acceptance\n'); p.chmod(0o644)
        registered = [api('/api/agent-instances', {'name': name, 'agent_type': 'dsh',
            'resources': [str(resource)], 'mode': 'controlled', 'environment': 'wsl'})
            for name in ('会话安全面板验收 A', '会话安全面板验收 B')]
        a, b = [api('/api/agent-instances/' + r['id'] + '/start', {}) for r in registered]
        path = '/api/agent-instances/' + a['id']
        for _ in range(2):
            api(path + '/sessions', {'resource': str(resource)})
        native = api(path + '/sessions')['sessions']; assert len(native) == 2
        sid = native[0]['id']; root = path + '/sessions/' + sid
        api(root + '/name', {'name': '真实备份会话 · 安全面板验收', 'expected_name': native[0].get('name')})
        page = api(root + '/policies'); assert len(page['security']['controls']) >= 3
        assert page['security']['session_local_supported'] is False
        assert probe(a)['outcome']['read_completed'] and probe(b)['outcome']['read_completed']
        report.update(instance_id=a['id'], other_instance_id=b['id'], session_id=sid, other_session_id=native[1]['id'])
        original_a, original_b = identity(api(path)), identity(api('/api/agent-instances/' + b['id']))
        body = {'scope': 'agent', 'operation': 'add', 'basis_hash': page['security']['basis_hash'],
                'request_key': uuid.uuid4().hex, 'acknowledge_scope': True,
                'rule': {'action': 'read', 'effect': 'deny', 'target': '/w/0/.agentscope-dsl-block.txt', 'text': '隔离验收凭据读取保护'}}
        created = api(root + '/security/proposals', body)
        assert api(root + '/security/proposals', body)['approval_id'] == created['approval_id']
        assert identity(api(path)) == original_a and identity(api('/api/agent-instances/' + b['id'])) == original_b
        receipt = approve(created)
        assert identity(api(path)) == original_a
        report['checks']['proposal_and_approval_do_not_execute'] = True
        apply(created, receipt)
        current = api(path); blocked = probe(current)
        assert not blocked['outcome']['read_completed']
        assert probe(b)['outcome']['read_completed']
        assert identity(api('/api/agent-instances/' + b['id'])) == original_b
        events = broker({'action': 'agent-instance-kernel-events', 'instance_id': current['id'],
                         'generation': current['generation'], 'cursor': None})
        assert events['generation'] == current['generation'] and events['domain_id'] == current['domain_id']
        denials = [entry['event'] for entry in events['events'] if entry['event'].get('blocked') and entry['event'].get('op') == 'read']
        assert any('.agentscope-dsl-block.txt' in event.get('rule', {}).get('clause_text', '') and
                   event.get('process_domain_id') == current['domain_id'] for event in denials)
        report['kernel_events'] = events
        report['blocked_probe'] = blocked
        report['checks']['actual_read_denied_only_in_target_agent'] = True
        page = api(root + '/policies')
        assert api(path + '/sessions/' + native[1]['id'] + '/policies')['security']['controls']
        selected = next(c for c in page['security']['controls'] if c['kind'] == 'typed' and c['rule']['action'] == 'read')
        removal = api(root + '/security/proposals', {'scope': 'agent', 'operation': 'disable',
            'constraint_id': selected['id'], 'basis_hash': page['security']['basis_hash'],
            'request_key': uuid.uuid4().hex, 'acknowledge_scope': True})
        assert probe(current)['outcome']['read_completed'] is False
        receipt = approve(removal); apply(removal, receipt)
        assert probe(api(path))['outcome']['read_completed']
        assert identity(api('/api/agent-instances/' + b['id'])) == original_b
        report['checks']['visual_disable_uses_new_approval_and_preserves_other_agent'] = True
        report['checks']['all_native_sessions_inherit_actual_agent_scope'] = True
        assert production_snapshot() == before
        report['checks']['production_unchanged'] = True
        report['passed'] = True
    finally:
        report['production_after'] = production_snapshot()
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2)); REPORT.chmod(0o600)
    print(json.dumps({'passed': report.get('passed', False), 'report': str(REPORT),
                      'instance_id': report.get('instance_id'), 'session_id': report.get('session_id')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
