"""Read-only product state. Never used to grant execution or application rights."""
from datetime import datetime, timedelta, timezone
from math import isfinite
from ..workspaces.observer import TTL

RUN_LABELS = {'stopped': '未运行', 'starting': '启动中', 'running': '运行中',
              'paused': '执行暂停', 'failed': '启动失败', 'unknown': '状态未知'}
LOAD_LABELS = {'loaded': '已加载', 'checking': '核验中', 'unverified': '未核验',
               'stopped': '未运行', 'observed': '仅观测'}
CONFIG_LABELS = {'draft': '草案', 'pending': '待审批', 'approved': '待应用',
                 'applying': '应用中', 'applied': '已应用', 'rejected': '已拒绝',
                 'stale': '需重新校验', 'invalid': '校验未通过',
                 'failed': '应用失败', 'blocked': '暂不可应用'}
PRODUCTS = {'dsh': 'DeepSeek Harness', 'hermes': 'Hermes', 'codex': 'Codex',
            'hermes-desktop': 'Hermes Desktop', 'other': '其他 Agent'}


def observation(row):
    observed = row.get('observed_at') or row.get('last_checked_at')
    try:
        stamp = datetime.fromisoformat(observed.replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        expiry = stamp + timedelta(seconds=TTL)
        age = row.get('evidence_age_seconds')
        fresh = (isinstance(age, (int, float)) and not isinstance(age, bool)
                 and isfinite(age) and 0 <= age < TTL
                 and datetime.now(timezone.utc) < expiry
                 and row.get('status') not in ('unknown', 'stale', 'unresponsive'))
        return {'observed_at': observed, 'expires_at': expiry.isoformat(),
                'ttl_seconds': TTL, 'fresh': fresh}
    except (TypeError, ValueError, AttributeError):
        return {'observed_at': observed, 'expires_at': None,
                'ttl_seconds': TTL, 'fresh': False}


def runtime(row):
    evidence = observation(row)
    # Closed is written only after a trusted stop, or at initial registration.
    # An unreachable control interface on an otherwise open instance is unknown.
    if row.get('gate') == 'closed' and not row.get('connected'):
        state = 'stopped'
    elif row.get('last_lifecycle_event') == 'start_failed':
        state = 'failed'
    elif not evidence['fresh']:
        state = 'unknown'
    elif row.get('status') == 'offline':
        state = 'stopped'
    elif row.get('gate') == 'failed':
        state = 'failed'
    elif row.get('gate') in ('starting', 'updating') or row.get('status') == 'starting':
        state = 'starting'
    elif row.get('connected') is True:
        state = 'paused' if row.get('gate') == 'paused' or row.get('execution_status', {}).get('gate') == 'closed' else 'running'
    else:
        state = 'unknown'
    return {'state': state, 'label': RUN_LABELS[state], **evidence}


def current_load(row, receipt):
    run = runtime(row)
    state = ('observed' if row.get('mode') != 'controlled' else
             'stopped' if run['state'] == 'stopped' else
             'checking' if run['state'] == 'starting' else 'unverified')
    result = {**observation(row), 'state': state, 'label': LOAD_LABELS[state],
              'instance_id': row.get('id'), 'generation': row.get('generation')}
    if state in ('observed', 'stopped') or not result['fresh'] or not receipt:
        return result
    artifact = receipt.get('artifact') or {}
    binding = artifact.get('binding') or {}
    live = row.get('runtime') or {}
    loaded = live.get('policy_artifact') or {}
    # Every identity component is required. A legacy PID-only receipt remains
    # readable as history, but is not evidence of the current process.
    identity = ('generation', 'domain_id', 'pid', 'start_ticks', 'boot_id', 'host_id')
    matched = all(row.get(k) is not None and row.get(k) != ''
                  and row[k] == binding.get(k) == live.get(k) for k in identity)
    verified = (matched and row.get('connected') is True and row.get('verified') is True
                and row.get('gate') in ('open', 'paused')
                and receipt.get('instance_id') == row.get('id')
                and receipt.get('generation') == row.get('generation')
                and artifact.get('loaded') is True and loaded.get('loaded') is True
                and bool(receipt.get('bundle_hash'))
                and receipt['bundle_hash'] == artifact.get('bundle_hash') == loaded.get('bundle_hash')
                # No imported DSL is represented by an explicit null hash.
                # The nonempty bundle hash still identifies compiled startup rules.
                and all('dsl_hash' in value for value in (receipt,artifact,row,live))
                and receipt['dsl_hash'] == artifact.get('dsl_hash') == row.get('dsl_hash') == live.get('dsl_hash')
                and (row.get('supervision') != 'broker-admission-v1'
                     or row.get('execution_status', {}).get('protection_fresh') is True))
    if verified:
        result.update(state='loaded', label=LOAD_LABELS['loaded'],
                      bundle_hash=receipt['bundle_hash'], loaded_at=receipt.get('created_at'))
    return result


def configuration(row):
    state = row.get('status', 'draft')
    if (state in ('draft','library') and not row.get('applied')
            and (row.get('execution_support', {}).get('applicable') is False or row.get('scope') == 'workspace')):
        state = 'blocked'
    elif row.get('validation_error'):
        state = 'invalid'
    elif row.get('applied') and not row.get('has_changes'):
        # A pending disable is still pending, not an application of that change.
        if state not in ('pending', 'approved', 'applying', 'failed', 'stale'):
            state = 'applied'
    if state not in CONFIG_LABELS:
        state = 'blocked'
    return {'schema': 'ConfigurationProgress/1', 'state': state,
            'label': CONFIG_LABELS[state], 'revision': row.get('revision'),
            'applied_revision': row.get('applied_revision'),
            'lifecycle': {'archived': bool(row.get('archived')),
                          'disabled': bool(row.get('disabled'))},
            'read_only': bool(row.get('read_only'))}


def display_identities(rows):
    def base(row):
        kind = PRODUCTS.get(row.get('agent_type'), 'Agent')
        name = (row.get('name') or '').strip()
        return name + ' · ' + kind if name and name != kind else kind
    names = [base(row) for row in rows]
    for row, name in zip(rows, names):
        # Stable suffix; never use PID as an instance discriminator.
        suffix = str(row['id']).removeprefix('instance-')
        length = 8
        while any(r['id'] != row['id'] and str(r['id']).removeprefix('instance-')[:length] == suffix[:length] for r in rows):
            length += 1
        row['display_name'] = name + (' · ' + suffix[:length] if not row.get('name') or names.count(name) > 1 else '')
