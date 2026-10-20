"""Read-only links from an exact configuration binding to its approval record."""
def link(con, ident, revision, scope, kind):
    table = {'template':'template_configuration_proposals', 'legacy':'system_policy_library_proposals'}[kind]
    rows = con.execute(f'''SELECT p.proposal_id, json_extract(s.value,'$.revision') AS revision
        FROM {table} p, json_each(p.selections_json) s
        JOIN instance_dsl_proposals d ON d.id=p.proposal_id
        WHERE json_extract(s.value,'$.id')=? AND d.scope_id=?
        ORDER BY p.rowid DESC''', (ident, scope)).fetchall()
    current = next((r for r in rows if r['revision'] == revision), None)
    chosen = current or (rows[0] if rows else None)
    return {'approval_id':chosen['proposal_id'] if chosen else None,
            'approval_revision':chosen['revision'] if chosen else None,
            'approval_current':current is not None}


def state(linked, fallback):
    if not linked['approval_current']:
        return fallback
    from .approval_views import detail
    return detail(linked['approval_id'])['status']


def disabled(con, ident, scope, kind):
    """Only a successfully applied removal is a disabled lifecycle marker."""
    table = {'template':'template_configuration_proposals', 'legacy':'system_policy_library_proposals'}[kind]
    rows = con.execute(f"""SELECT p.*, d.documents_json FROM {table} p
        JOIN instance_dsl_proposals d ON d.id=p.proposal_id
        WHERE d.scope_id=? AND d.state='applied' ORDER BY d.rowid DESC""",(scope,)).fetchall()
    import json
    for row in rows:
        if any(s['id']==ident for s in json.loads(row['selections_json'])):
            return not any(d['id']==ident for d in json.loads(row['documents_json']))
    return False
