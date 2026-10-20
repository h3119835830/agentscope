"""Server-owned conversation lineage. Browser prose is not a file-read receipt."""
import json
from .. import db
from . import workspace_references as refs


def load(request_id):
    with db.connect() as con:
        rows = con.execute("""SELECT result_json FROM template_configuration_requests
            WHERE state='completed' AND request_key LIKE 'generate:%'
            AND json_extract(result_json,'$.request_id')=? LIMIT 2""", (request_id,)).fetchall()
    if len(rows) != 1:
        raise ValueError('此前场景记录不存在或不唯一，请开始新场景')
    return json.loads(rows[0][0])


def restore(scope_id, body, basis):
    """Rehydrate at most three exact turns and the parent's cumulative receipts.

    Receipt verification checks current generation, resources, policy, identity,
    inode and content. A stale parent must never fall back to a fresh unbound run.
    Historical records without a basis remain viewable but cannot be resumed.
    """
    request_id = body.get('parent_request_id')
    if not request_id:
        return [], [], None
    parent = load(request_id)
    turns = []
    current = parent
    for _ in range(3):
        expected = {'scope_id': scope_id, 'scope': body['scope'],
                    'workspace_id': body.get('workspace_id'),
                    'reference_workspace_id': body.get('reference_workspace_id'),
                    'stage': body.get('stage', 'preflight')}
        if any(current.get(k, 'preflight' if k == 'stage' else None) != v for k, v in expected.items()):
            raise ValueError('此前场景不属于当前 Agent、资料范围或阶段，请开始新场景')
        if current.get('generation_basis') != basis:
            raise ValueError('此前场景的资源、运行代次或策略已变化，请开始新场景重新读取')
        turns.append({'request_id': current['request_id'], 'requirements': current['text'],
                      'summary': current.get('summary',''),
                      'questions': current['questions'], 'gaps': current['gaps'],
                      'configurations': current.get('configuration_snapshots', []),
                      'sources': current.get('reference_reads', [])})
        previous = current.get('parent_request_id')
        if not previous:
            break
        current = load(previous)
    references = []
    for source in parent.get('reference_reads', []):
        reference = refs.for_model(scope_id, source['id'])
        if reference['snapshot_hash'] != source['snapshot_hash']:
            raise ValueError('此前场景的读取依据已变化，请重新读取')
        references.append(reference)
    return list(reversed(turns)), references, parent['request_id']
