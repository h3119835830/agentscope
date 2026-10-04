"""Source-backed conversion inputs. Metadata previews have no execution authority."""
import hashlib
import json
import re
import uuid
from pathlib import PurePosixPath
from .. import db
from . import sources
from .models import MarkdownDocument, Origin, Statement, StrategyStatementVersion
from .pipeline import digest, render_policy_record, verify_evidence

def directory_preview(row):
    current=row.get('statement_version');statement=current['record']['statement'] if current else None
    record={"id":row['id'],"version":current['version'] if current else row['revision'],
        "metadata":{"origin":current['record']['origin'] if current else {"repository":row['source_repo'],"commit":row['source_commit'],"path":row['source_path']},
            "labels":{"level":statement['enforcement_level'] if statement else row['category'],"context":statement['context_requirement'] if statement else row['context_scope'],"classification":"metadata labels; not a translated rule"},
            "evidence":{"statement_text":statement['text_original'] if statement else row['text'],"lines":[row['line_start'],row['line_end']],
                "located_at_import":bool(row['source_verified']),"file_hash":row['source_content_sha256']}},
        "candidate_rule":{"source":"unresolved","target":"unresolved","effect":"none","reason":statement['text_original'] if statement else row['text']},
        "compile_check":{"state":"not_generated","diagnostics":["Metadata preview only; no translated rule or executable DSL."]},
        "governance":{"status":row['status'],"authority":"directory_preview","executable":False}}
    return {"kind":"directory_metadata_preview","executable":False,"pseudo_code":render_policy_record(record)}

def snapshot(document,scope_path='',requested_ref='manual-input'):
    raw=document.text.encode();origin=document.origin
    dest=sources.ROOT/origin.repository/origin.commit/origin.path
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():
        if dest.read_bytes()!=raw:raise ValueError('不可变输入快照内容冲突')
    else:
        with dest.open('xb') as handle:handle.write(raw)
        dest.chmod(0o440)
    with db.connect() as con:
        con.execute('INSERT OR IGNORE INTO history_documents VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            (origin.document_id,origin.repository,requested_ref,origin.commit,origin.path,scope_path,str(dest),
             origin.content_hash,len(raw),origin.url,db.now()))
        ident=con.execute('SELECT id FROM history_documents WHERE repository=? AND commit_sha=? AND relative_path=? AND content_sha256=?',
            (origin.repository,origin.commit,origin.path,origin.content_hash)).fetchone()[0]
    return document.model_copy(update={'origin':origin.model_copy(update={'document_id':ident})})

def store_version(strategy_id,document,statement,scope_path='',actor='研究者'):
    with db.connect() as con:
        from .catalog import mutable_strategy
        mutable_strategy(con,strategy_id)
        latest=con.execute('SELECT * FROM strategy_statement_versions WHERE strategy_id=? ORDER BY version DESC LIMIT 1',(strategy_id,)).fetchone()
        prior=json.loads(latest['record_json']) if latest else None
        if prior and prior['statement']==statement.model_dump() and prior['origin']==document.origin.model_dump() and not prior['resolved_context']:
            return {'id':latest['id'],'strategy_id':strategy_id,'status':latest['review_status'],'reused':True}
        version=(latest['version']+1) if latest else 1
        record=StrategyStatementVersion(id=uuid.uuid4().hex,strategy_id=strategy_id,version=version,
            origin=document.origin,statement=statement,scope_path=scope_path)
        data=record.model_dump(exclude={'review_status'})
        con.execute('INSERT INTO strategy_statement_versions(id,strategy_id,version,document_id,record_json,content_sha256,review_status,created_at) VALUES(?,?,?,?,?,?,?,?)',
            (record.id,strategy_id,version,document.origin.document_id,json.dumps(data,ensure_ascii=False),digest(data),'pending_review',db.now()))
        db.audit(con,None,'history_input_registered',actor,{'strategy_id':strategy_id,'statement_version_id':record.id,'document_id':document.origin.document_id})
        return {'id':record.id,'strategy_id':strategy_id,'status':'pending_review','reused':False}

def statement_from(values,text,quote,start,end):
    language='zh' if re.search(r'[\u4e00-\u9fff]',text) else 'en'
    return Statement(source_quote=quote,line_start=start,line_end=end,text_original=text,
        text_zh=values.get('text_zh','') or (text if language=='zh' else ''),
        text_en=values.get('text_en','') or (text if language=='en' else ''),language=language,
        content_type='policy',policy_kind='constraint',topics=[],enforcement_level=values['enforcement_level'],
        context_requirement=values['context_requirement'])

def prepare_record(ident,values,actor):
    from .catalog import mutable_strategy
    from ..services import corpus
    with db.connect() as con:row=mutable_strategy(con,ident)
    if row['source_kind']=='manual':
        document,statement=manual_document(row['text'],values)
        document=snapshot(document)
        return store_version(ident,document,statement,actor=actor)
    if row['source_kind']!='rq1_corpus' or not row['source_verified']:
        raise ValueError('只有已定位原文的 RQ1 目录记录可准备转换输入')
    source=None
    for _,_,repo in corpus.load_local():
        if not repo or repo.get('repo','').lower()!=row['source_repo'].lower():continue
        file=next((f for f in repo.get('files',[]) if f.get('path')==row['source_path'] and f.get('last_commit_sha')==row['source_commit']),None)
        if file:
            _,source=corpus.fetch_one((repo,file));break
    if source is None or hashlib.sha256(source.encode()).hexdigest()!=row['source_content_sha256']:
        raise ValueError('固定来源快照不可用或 hash 不一致')
    lines=source.splitlines(keepends=True);start=row['line_start'];end=row['line_end']
    if not start or not end or end<start or end>len(lines):raise ValueError('来源行范围无效')
    quote=''.join(lines[start-1:end]).rstrip('\r\n')
    needle=corpus.normal(row['text']);haystack=corpus.normal(quote)
    if not needle or not (needle in haystack or haystack in needle and len(haystack)>50):
        raise ValueError('目录语句与固定来源行不匹配')
    document_id='rq1-input-'+digest([row['source_repo'],row['source_commit'],row['source_path'],row['source_content_sha256']])
    origin=Origin(document_id=document_id,repository=row['source_repo'],commit=row['source_commit'],path=row['source_path'],
        content_hash=row['source_content_sha256'],url=(row['raw_url'] or '').split('#')[0])
    document=MarkdownDocument(text=source,origin=origin)
    scope=str(PurePosixPath(row['source_path']).parent) if '/' in row['source_path'] else ''
    statement=verify_evidence(document,statement_from(values,row['text'],quote,start,end))
    if statement.evidence_state!='verified':raise ValueError('精确来源证据未通过核验')
    document=snapshot(document,scope,'rq1-fixed-source')
    return store_version(ident,document,statement,scope,actor)

def manual_document(text,values):
    text=text.strip()
    if len(text)<5:raise ValueError('策略内容至少五个字符')
    task_id=values.get('task_id');task=None
    if task_id:
        with db.connect() as con:task=con.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
        if not task or task['status'] not in ('prepared','policy_review','approved'):raise ValueError('输入只能关联尚未启动的任务')
    identity=uuid.uuid4().hex;sha=hashlib.sha256(text.encode()).hexdigest()
    origin=Origin(document_id='manual-input-'+identity,repository=task['repo'] if task else 'manual/local',
        commit=task['commit_sha'] if task else sha[:40],path='manual-input/'+identity+'.md',content_hash=sha)
    document=MarkdownDocument(text=text,origin=origin)
    statement=verify_evidence(document,statement_from(values,text,text,1,text.count('\n')+1))
    return document,statement

def create_input(values,actor):
    from .catalog import create
    text=values['text'].strip()
    document,statement=manual_document(text,values)
    document=snapshot(document)
    level=values['enforcement_level'].replace('_','-')
    row=create({'text':text,'category':level,'context_scope':values['context_requirement'].replace('_','-'),
        'execution_layer':'manual_instruction'},actor)
    return store_version(row['id'],document,statement,actor=actor)
