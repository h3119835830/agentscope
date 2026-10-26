"""One immutable configuration revision per approval display record."""
import json
from fastapi import HTTPException
from .. import db
from .generation_snapshots import freeze
from .policy import digest


def records(proposal):
    from . import template_configurations as configurations
    with db.connect() as con:
        binding = con.execute('SELECT selections_json FROM template_configuration_proposals WHERE proposal_id=?', (proposal['id'],)).fetchone()
        if not binding:
            return []
        result = []
        for selection in json.loads(binding[0]):
            try:
                row = configurations.load(selection['id'], selection['revision'], con)
                if row['scope_id'] != proposal['scope_id'] or digest(row['document']) != selection['document_hash']:
                    raise ValueError('审批配置版本不一致')
                payload = json.loads(con.execute('SELECT payload_json FROM template_configuration_versions WHERE id=? AND revision=?', (row['id'], row['revision'])).fetchone()[0])
                snapshot = freeze(row['id'], row['revision'], payload, row['scope_id'], row['scope'])
                result.append({**snapshot, 'approval_operation':selection.get('operation','apply')})
            except (HTTPException, ValueError, KeyError):
                result.append({'id':selection['id'], 'revision':selection['revision'], 'unavailable':True})
        return result
