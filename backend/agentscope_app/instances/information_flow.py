"""Bounded witness queries. No edge is inferred from paths, PID or chronology."""
import json
import re
from .. import db
from . import sessions,dsl_policy
from .policy import digest


def node_key(event, node):
    kind=node.get('kind')
    if kind=='process':
        identity=[kind,node.get('pid'),node.get('start_boottime_ns')]
    elif kind=='file':
        identity=[kind,node.get('device'),node.get('inode'),node.get('inode_generation')]
    elif kind=='endpoint':
        identity=[kind,node.get('address')]
    else:
        identity=['operation',event['event_id']]
    return digest([event.get('stream_id'),event.get('domain_id'),identity])


def mappings(saved):
    mapping={}
    if not saved:
        return mapping
    for doc in saved['artifact'].get('documents',[]):
        names=re.findall(r'^source ([a-zA-Z0-9_]+) =',doc.get('effective_dsl',''),re.M)
        for name in names:
            public=next((label for label in ('AGENT','SECRET','SENSITIVE','REMOTE','CODE') if name.endswith('_'+label)),name)
            mapping[name]={'label':public,'document_id':doc['id'],'configuration_name':doc.get('name'),
                           'sources':doc.get('label_sources',[]) if public=='SECRET' else [],
                           'historical':public in ('SENSITIVE','REMOTE','CODE')}
    return mapping


def attribution(con,ident,gen,event):
    tag=str(event.get('tool_call_tag') or '')
    if tag in ('','0'):
        return None
    rows=con.execute("""SELECT session_id,call_id,detail_json FROM instance_events
        WHERE instance_id=? AND generation=? AND kind='tool_start'
        AND CAST(json_extract(detail_json,'$.kernel_call_tag') AS TEXT)=?""",(ident,gen,tag)).fetchall()
    matches={(r['session_id'],r['call_id']) for r in rows if json.loads(r['detail_json']).get('domain_id')==event.get('process_domain_id')}
    return next(iter(matches))[0] if len(matches)==1 else None


def project(con,raw,saved,ident,gen):
    event=json.loads(raw['event_json'])
    if event.get('event')!='label_transition' or event.get('schema_version')!=1:
        return None
    if not saved or raw['generation']!=saved['generation'] or raw['bundle_hash']!=saved['bundle_hash']:
        return None
    binding=saved['artifact'].get('binding',{})
    if event.get('generation')!=gen or event.get('policy_hash')!=raw['bundle_hash'] or event.get('process_domain_id')!=raw['domain_id'] or raw['domain_id']!=binding.get('domain_id'):
        return None
    if not isinstance(event.get('event_id'),str) or not isinstance(event.get('stream_id'),str):
        return None
    if not all(isinstance(event.get(k),dict) for k in ('subject','object')):
        return None
    mapping=mappings(saved)
    names=event.get('label_names',[])
    mapped=[mapping[n] for n in names if n in mapping]
    # Unknown label mappings remain inspectable but can never be a complete chain.
    return {**event,'audit_id':raw['id'],'time':event.get('timestamp_unix_ns') or raw['created_at'],
            'session_id':attribution(con,ident,gen,event),'source_mapping':mapped,
            'mapping_complete':bool(names) and len(mapped)==len(names)}


def query(ident,sid,view='session',generation=None,label=None,anchor=None,cursor=None,limit=24):
    row,session,gen,active=sessions.session_context(ident,sid,generation)
    collection=sessions.collect_kernel(row) if gen==row.get('generation') else {'available':True,'historical':True}
    saved=dsl_policy.receipt(ident,gen)
    base={'view':view,'generation':gen,'historical':not active,'collection':collection,'nodes':[],'edges':[],
          'anchors':[],'next_cursor':None,'integrity':{'state':'empty','reasons':[]},
          'scope_label':'当前会话 · 仅可信关联事件' if view=='session' else 'Agent 共享执行域 · 不代表当前会话独有行为'}
    if view not in ('session','shared_domain'):
        raise ValueError('信息流范围不合法')
    def visible(e):
        return e and (view=='shared_domain' or e['session_id']==sid)
    with db.connect() as con:
        rows=con.execute("""SELECT * FROM instance_kernel_events WHERE instance_id=? AND generation=?
            AND json_extract(event_json,'$.event')='label_transition'
            AND json_extract(event_json,'$.operation')='rule_match'
            ORDER BY id DESC LIMIT 500""",(ident,gen)).fetchall()
        seen=set()
        for raw in rows:
            e=project(con,raw,saved,ident,gen)
            if not visible(e) or e['event_id'] in seen:
                continue
            seen.add(e['event_id'])
            mapped=e['source_mapping']
            if label and label not in e.get('label_names',[]) and label not in {m['label'] for m in mapped}:
                continue
            base['anchors'].append({'event_id':e['event_id'],'label_names':e.get('label_names',[]),
                                    'labels':[m['label'] for m in mapped],'time':e['time'],'outcome':e['outcome'],
                                    'target':e.get('target') or e['object'].get('address','')})
            if len(base['anchors'])>=50:break
        if not anchor and base['anchors']:
            anchor=base['anchors'][0]['event_id']
        if not anchor:
            legacy=con.execute("""SELECT 1 FROM instance_kernel_events WHERE instance_id=? AND generation=?
                AND json_extract(event_json,'$.event')='taint_violation' LIMIT 1""",(ident,gen)).fetchone()
            # Modern shared-domain receipts are not legacy just because none can
            # be attributed to this session (or match the selected label).
            modern=con.execute("""SELECT 1 FROM instance_kernel_events WHERE instance_id=? AND generation=?
                AND json_extract(event_json,'$.event')='label_transition'
                AND json_extract(event_json,'$.schema_version')=1 LIMIT 1""",(ident,gen)).fetchone()
            base['integrity']['state']='collection_failed' if collection.get('error') else 'legacy' if legacy and not modern else 'unsupported' if collection.get('transitions_supported') is False or not collection.get('available') else 'empty'
            return base
        def lookup(event_id):
            raw_rows=con.execute("""SELECT * FROM instance_kernel_events WHERE instance_id=? AND generation=?
                AND json_extract(event_json,'$.event_id')=? ORDER BY id LIMIT 1001""",(ident,gen,event_id)).fetchall()
            if not raw_rows:
                return None,'missing_predecessor'
            if len(raw_rows)>1000:
                return None,'duplicate_limit'
            if len({digest(json.loads(r['event_json'])) for r in raw_rows})!=1:
                return None,'conflicting_duplicate'
            value=project(con,raw_rows[0],saved,ident,gen)
            if not visible(value):
                return None,'shared_context_not_in_session' if value else 'unverified_receipt'
            return value,None
        selected,problem=lookup(anchor)
        if problem or selected.get('operation')!='rule_match':
            raise ValueError('锚点不属于此运行代次、范围或可信策略命中')
        base['anchor']=anchor
        # Cursor is validated by walking from this anchor (bounded), never an
        # arbitrary event shortcut. A page cannot switch label/domain/stream.
        current=selected;visited=set();reasons=['collector_loss'] if collection.get('lost_events') else [];edges=[];nodes={};skipping=bool(cursor)
        for _ in range(512):
            if current['event_id'] in visited:
                reasons.append('cycle');break
            visited.add(current['event_id'])
            if current['event_id']==cursor:skipping=False
            if not skipping:
                if len(edges)>=limit:
                    base['next_cursor']=current['event_id'];break
                if not current.get('identity_complete'):reasons.append('identity_or_predecessor_missing')
                if not current.get('mapping_complete'):reasons.append('label_mapping_missing')
                if int(current.get('lost_total','0')):reasons.append('collector_loss')
                a=node_key(current,current['subject']);b=node_key(current,current['object'])
                for key,node in ((a,current['subject']),(b,current['object'])):
                    title=current['target'] if node['kind']=='file' else node.get('address') if node['kind']=='endpoint' else '进程 '+str(node.get('pid')) if node['kind']=='process' else '策略命中'
                    nodes.setdefault(key,{'id':key,'kind':node['kind'],'title':title or node['kind'],'identity':node})
                edges.append({'id':current['event_id'],'from':a,'to':b,'operation':current['operation'],
                              'hook':current.get('hook'),'outcome':current.get('outcome'),'time':current['time'],
                              'label_names':current.get('label_names',[]),'source_mapping':current['source_mapping'],
                              'policy_hash':current['policy_hash'],'domain_id':current['domain_id'],
                              'evidence_ref':current['audit_id'],'session_id':current['session_id'],
                              'generation':gen,'monotonic_ns':current['monotonic_ns']})
            parent_id=current.get('predecessor_event_id')
            if not parent_id:
                if not current.get('root_source'):reasons.append('missing_origin')
                if skipping:raise ValueError('游标不属于此锚点的来源链')
                break
            parent,problem=lookup(parent_id)
            if problem:
                reasons.append(problem);break
            if any(parent.get(k)!=current.get(k) for k in ('stream_id','domain_id','label_mask')) or node_key(parent,parent['object'])!=node_key(current,current['subject']) or int(parent['monotonic_ns'])>int(current['monotonic_ns']):
                reasons.append('predecessor_identity_mismatch');break
            current=parent
        else:
            reasons.append('chain_limit')
        if skipping:
            raise ValueError('游标无法在当前可信来源链中核验')
        base.update(nodes=list(nodes.values()),edges=list(reversed(edges)),
                    integrity={'state':'incomplete' if reasons else 'paged' if base['next_cursor'] else 'complete',
                               'reasons':sorted(set(reasons))})
    return base
