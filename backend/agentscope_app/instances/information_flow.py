"""Project native ActPlane rule matches and single-hop provenance.

ActPlane propagates labels in the kernel, but its supported audit contract emits
rule matches with at most the first available origin for one matched label. This
module deliberately does not reconstruct a causal chain from paths, PIDs or time.
"""
import json
import re

from .. import db
from . import dsl_policy, sessions


PUBLIC_LABELS = ('AGENT', 'SECRET', 'SENSITIVE', 'REMOTE', 'CODE')
MAX_SCAN = 1000
LABEL_SCAN = 500


def mappings(saved):
    result = {}
    if not saved:
        return result
    for doc in saved['artifact'].get('documents', []):
        names = re.findall(r'^source ([a-zA-Z0-9_]+) =', doc.get('effective_dsl', ''), re.M)
        for name in names:
            public = next((label for label in PUBLIC_LABELS if name == label or name.endswith('_' + label)), name)
            result[name] = {
                'label': public,
                'document_id': doc['id'],
                'configuration_name': doc.get('name'),
                'sources': doc.get('label_sources', []) if public == 'SECRET' else [],
                'historical': public in ('SENSITIVE', 'REMOTE', 'CODE'),
            }
    return result


def raw_label_names(event):
    names = event.get('matched_label_names')
    if isinstance(names, list):
        return list(dict.fromkeys(str(name) for name in names if isinstance(name, str) and name))
    name = event.get('matched_label_name')
    if isinstance(name, str) and name:
        return [name]
    details = event.get('matched_label_details')
    if isinstance(details, list):
        return list(dict.fromkeys(str(item['label']) for item in details
                                  if isinstance(item, dict) and isinstance(item.get('label'), str) and item['label']))
    return []


def public_label(name, mapping):
    return mapping.get(name, {}).get('label', name)


def source_configuration(names, mapping):
    documents = []
    by_id = {}
    for name in names:
        value = mapping.get(name)
        if not value:
            continue
        key = value['document_id']
        document = by_id.get(key)
        if document is None:
            document = {'id': key, 'name': value.get('configuration_name'), 'labels': [],
                        'sources': [], 'historical': False}
            by_id[key] = document
            documents.append(document)
        if value['label'] not in document['labels']:
            document['labels'].append(value['label'])
        known = {(source.get('id'), source.get('version')) for source in document['sources']}
        document['sources'].extend(source for source in value.get('sources', [])
                                   if (source.get('id'), source.get('version')) not in known)
        document['historical'] = document['historical'] or value.get('historical', False)
    return {
        'names': list(dict.fromkeys(doc.get('name') for doc in documents if doc.get('name'))),
        'documents': documents,
    }


def native_provenance(event, mapping):
    value = event.get('provenance')
    if not isinstance(value, dict):
        return 'not_reported', None
    return 'reported_first_origin', {
        'label': public_label(value.get('label'), mapping) if isinstance(value.get('label'), str) else value.get('label'),
        'origin_pid': value.get('origin_pid'),
        'origin_op': value.get('origin_op'),
        'origin_target': value.get('origin_target'),
        'origin_timestamp_ns': str(value['origin_timestamp_ns']) if value.get('origin_timestamp_ns') is not None else None,
    }


def project(row, saved, raw):
    event = json.loads(raw['event_json'])
    if event.get('event') != 'taint_violation':
        return None
    match = sessions.project_kernel(row, saved, raw)
    # Product evidence must bind to the exact loaded generation, bundle,
    # process domain and compiled clause.
    if not match.get('source_refs'):
        return None
    mapping = mappings(saved)
    names = raw_label_names(event)
    labels = list(dict.fromkeys(public_label(name, mapping) for name in names))
    provenance_state, provenance = native_provenance(event, mapping)
    return {
        'id': raw['id'],
        'time': event.get('timestamp_unix_ns') or raw['created_at'],
        'labels': labels,
        'raw_label_names': names,
        'provenance_state': provenance_state,
        'provenance': provenance,
        'match': {
            'operation': match.get('operation'),
            'target': match.get('target'),
            'pid': match.get('pid'),
            'rule_id': match.get('rule_id'),
            'rule_name': match.get('rule_name'),
            'policy_name': match.get('policy_name'),
            'effect': match.get('effect'),
            'actual_action': match.get('actual_action'),
            'blocked': match.get('blocked', False),
            'killed': match.get('killed', False),
        },
        'binding': {
            'domain_id': match.get('domain_id'),
            'bundle_hash': match.get('bundle_hash'),
            'session_id': match.get('session_id'),
            'attribution': match.get('attribution'),
        },
        'source_configuration': source_configuration(names, mapping),
        'evidence_ref': raw['id'],
    }


def visible(record, sid, view):
    return record is not None and (view == 'shared_domain' or record['binding']['session_id'] == sid)


def recent_labels(con, row, saved, ident, gen, sid, view):
    labels = []
    rows = con.execute("""SELECT * FROM instance_kernel_events
        WHERE instance_id=? AND generation=?
        AND json_extract(event_json,'$.event')='taint_violation'
        ORDER BY id DESC LIMIT ?""", (ident, gen, LABEL_SCAN)).fetchall()
    for raw in rows:
        record = project(row, saved, raw)
        if not visible(record, sid, view):
            continue
        for label in record['labels']:
            if label not in labels:
                labels.append(label)
    return labels


def query(ident, sid, view='session', generation=None, label=None, cursor=None, limit=24):
    if view not in ('session', 'shared_domain'):
        raise ValueError('信息流范围不合法')
    if cursor is not None and (type(cursor) is not int or cursor < 1):
        raise ValueError('信息流游标不合法')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('信息流分页大小不合法')

    row, session, gen, _active = sessions.session_context(ident, sid, generation)
    historical = bool(session.get('historical') or gen != row.get('generation'))
    collection = sessions.collect_kernel(row) if gen == row.get('generation') else {'available': True, 'historical': True}
    saved = dsl_policy.receipt(ident, gen)
    records = []
    scanned = 0
    before = cursor

    with db.connect() as con:
        available_labels = recent_labels(con, row, saved, ident, gen, sid, view)
        while len(records) <= limit and scanned < MAX_SCAN:
            rows = con.execute("""SELECT * FROM instance_kernel_events
                WHERE instance_id=? AND generation=?
                AND json_extract(event_json,'$.event')='taint_violation'
                AND (? IS NULL OR id<?)
                ORDER BY id DESC LIMIT 200""", (ident, gen, before, before)).fetchall()
            if not rows:
                break
            for raw in rows:
                scanned += 1
                record = project(row, saved, raw)
                if not visible(record, sid, view):
                    continue
                if label and label not in record['labels'] and label not in record['raw_label_names']:
                    continue
                records.append(record)
                if len(records) > limit:
                    break
            before = rows[-1]['id']
            if len(rows) < 200 or len(records) > limit:
                break

    more = len(records) > limit
    records = records[:limit]
    state = 'collection_failed' if not collection.get('available') else 'available' if records else 'empty'
    for record in records:
        # Raw compiler label names are used only for exact filtering. The
        # product contract exposes the mapped labels and native provenance.
        record.pop('raw_label_names', None)
    return {
        'view': view,
        'generation': gen,
        'historical': historical,
        'collection': collection,
        'state': state,
        'available_labels': available_labels,
        'records': records,
        'next_cursor': records[-1]['id'] if more and records else None,
        'coverage': 'ActPlane 原生事件仅证明当前规则命中及首个可用来源，不代表完整逐跳传播链。',
    }
