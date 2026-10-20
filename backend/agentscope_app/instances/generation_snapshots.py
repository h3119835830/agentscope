"""Frozen conversation content with read-only, exact-version approval status."""
import copy
import json
from fastapi import HTTPException
from .. import db
from . import template_catalog as catalog
from .policy import digest


def freeze(ident, revision, payload, scope_id, scope, agent=None):
    template = catalog.get(payload['template_id'], payload['template_version'])
    if digest(template) != payload['template_hash']:
        raise ValueError('生成时模板版本不一致')
    name = (agent.get('name') or agent.get('agent_type') or 'Agent') if agent else None
    return copy.deepcopy({
        'id': ident, 'revision': revision, 'name': payload['name'],
        'configuration_hash': digest(payload),
        'template': {'id': template['id'], 'version': template['version'], 'name': template['name'],
                     **({'fixed_fields':template['fixed_fields']} if 'fixed_fields' in template else {}),
                     'parameters': [{k: p[k] for k in ('key', 'label', 'type')} for p in template['parameters']]},
        'parameters': payload['parameters'],
        **({'execution_support': payload['execution_support']} if 'execution_support' in payload else {}),
        'scope': {'id': scope_id, 'type': scope,
                  'label': '所有 Agent' if scope == 'system' else
                           '历史工作区范围（独立应用暂不支持）' if scope == 'workspace' else
                           '指定 Agent · ' + name if name else '指定 Agent（历史名称未记录）'},
    })


def project(generation):
    """Never substitute today's configuration/template/Agent name for old content."""
    from . import template_configurations as configurations
    from .configuration_approvals import link, state
    snapshots = generation.get('configuration_snapshots')
    result = []
    for reference in generation['items']:
        snapshot = next((s for s in snapshots or [] if
                         (s['id'], s['revision']) == (reference['id'], reference['revision'])), None)
        try:
            row = configurations.load(reference['id'], reference['revision'])
            if row['scope_id'] != generation['scope_id'] or row['scope'] != generation['scope']:
                raise ValueError('历史配置归属不一致')
            with db.connect() as con:
                payload = json.loads(con.execute('SELECT payload_json FROM template_configuration_versions WHERE id=? AND revision=?',
                                                (row['id'], row['revision'])).fetchone()[0])
            if snapshot is None and snapshots is None:
                # Legacy histories retain exact immutable configuration/template versions.
                # They did not record the historical Agent display name.
                snapshot = freeze(row['id'], row['revision'], payload, row['scope_id'], row['scope'])
            if not snapshot or snapshot['scope']['id'] != row['scope_id'] or snapshot['scope']['type'] != row['scope']:
                raise ValueError('历史快照归属不一致')
            if snapshot['configuration_hash'] != digest(payload):
                raise ValueError('历史快照配置版本不一致')
            with db.connect() as con:
                linked = link(con, row['id'], row['revision'], row['scope_id'], 'template')
                approval = con.execute('SELECT selections_json FROM template_configuration_proposals WHERE proposal_id=?',
                                       (linked['approval_id'],)).fetchone() if linked['approval_current'] else None
            operation = next((s.get('operation', 'apply') for s in json.loads(approval[0])
                              if s['id'] == row['id'] and s['revision'] == row['revision']), 'apply') if approval else 'apply'
            status = state(linked, 'draft')
        except (HTTPException, ValueError, KeyError, RuntimeError, OSError):
            status, operation = 'unavailable', 'apply'
        result.append({**(snapshot or {'id': reference['id'], 'revision': reference['revision'], 'unavailable': True}),
                       'approval_status': status, 'approval_operation': operation})
    return {**generation, 'configuration_snapshots': result}
