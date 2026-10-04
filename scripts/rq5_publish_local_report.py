#!/usr/bin/env python3
"""Export public benchmark evidence, without credentials or native replay streams."""
import hashlib
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path
from rq5_service import ROOT, STATE

path=STATE/'report/acceptance.json';report=json.loads(path.read_text())
if report.get('six_dsh_runs')!=6:raise SystemExit('Complete the six formal runs before publishing the report')
con=sqlite3.connect(STATE/'acceptance.sqlite3');con.row_factory=sqlite3.Row
for case,pair in report['cases'].items():
    for group in ('A','B'):
        run=pair[group];task=run['id']
        proposal=con.execute('SELECT * FROM bootstrap_proposals WHERE id=?',(run['proposal_id'],)).fetchone()
        run['candidate']={'id':proposal['id'],'content_hash':proposal['content_hash'],'state':proposal['state'],
                          'proposal':json.loads(proposal['proposal_json']),'validation':json.loads(proposal['validation_json'])}
        version=con.execute('SELECT id,version,layer,dsl_text,policy_yaml,compile_state,compile_json,status,approved_by,approved_at FROM policy_versions WHERE id=?',(run['version']['id'],)).fetchone()
        run['approved_version']=dict(version);run['approved_version']['compile_result']=json.loads(run['approved_version'].pop('compile_json'))
        run['generator_tool_events']=[{'tool':r['tool'],'at':r['occurred_at'],'input':json.loads(r['input_json']),'output':json.loads(r['output_json'])} for r in con.execute('SELECT * FROM bootstrap_tool_events WHERE job_id=? ORDER BY occurred_at',(proposal['job_id'].removeprefix('derived:'),))]
report['manual_regression']=json.loads((STATE/'report/manual-regression.json').read_text())
report['minimum_probe']=json.loads((STATE/'minimal-probe/result.json').read_text())
isolation=STATE/'report/isolation.json'
if isolation.exists():report['isolation']=json.loads(isolation.read_text())
report['privacy']={'credentials_exported':False,'reasoning_exported':False,'native_sessions_exported':False,
                    'scope':'Fixed public synthetic benchmark assets, public assistant responses, observable actions and policy/event hashes'}
report['runtime_environment']={'kernel':subprocess.check_output(['uname','-r'],text=True).strip(),
                             'architecture':subprocess.check_output(['uname','-m'],text=True).strip(),
                             'actplane_version':subprocess.check_output([str(ROOT/'bin/actplane'),'--version'],text=True).strip(),
                             'actplane_binary_sha256':hashlib.sha256((ROOT/'bin/actplane').read_bytes()).hexdigest(),
                             'node_version':subprocess.check_output([str(ROOT/'bin/node'),'--version'],text=True).strip()}
destination=Path('/mnt/c/Users/happy/Desktop/归纳梳理/技术文档/REVIEW/AgentScope-RQ5-v1')
destination.mkdir(parents=True,exist_ok=True)
raw=json.dumps(report,ensure_ascii=False,indent=2);(destination/'evidence.json').write_text(raw)
evidence_hash=hashlib.sha256(raw.encode()).hexdigest()
payload=json.dumps(report,ensure_ascii=False).replace('<','\\u003c')
template='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AgentScope Pi 第二层 RQ5 验收报告</title>
<style>body{margin:0;background:#f3f5f8;color:#172335;font:15px/1.6 system-ui,sans-serif}main{max-width:1120px;margin:36px auto;padding:0 24px}h1{font-size:30px;line-height:1.3}h2{font-size:22px}p{max-width:960px}section{background:white;padding:24px;margin:20px 0;border:1px solid #dce3eb;border-radius:14px}table{border-collapse:collapse;width:100%}th,td{padding:12px;text-align:left;border-bottom:1px solid #e4e9f1}th{background:#f5f8fc}code{font-family:ui-monospace,monospace;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:520px;overflow:auto;background:#f4f6f9;padding:16px;font-size:12px}summary{cursor:pointer;padding:10px 0;font-weight:600}.good{color:#087e62}.bad{color:#b04728}.pills{display:flex;gap:12px;flex-wrap:wrap}.pills b{background:#eef4ff;border-radius:8px;padding:12px 18px}.note{color:#57667b}small{color:#5c687a}a{color:#2363b8}</style>
<main><h1>AgentScope Pi 第二层 RQ5 验收报告</h1><p>固定场景 → Pi 证据与历史检索 → 候选校验 → 按 hash 审批 → ActPlane 加载 → DSH 执行 → 独立评测。</p><p class="note">这是 RQ5 场景迁移至 AgentScope/DSH 的扩展验收。原实验采用 OpenHands；本版增加可见资产、平台限制和已审历史输入。链路通过、内核拒绝与任务修复分别统计。</p><div class="pills" id="totals"></div><div id="cases"></div><section><h2>隔离与回归</h2><div id="isolation"></div><p>只导出公开基准资产及可观察证据。管理员凭据、模型私有推理和原生 replay 流不在报告中。</p><p><a href="evidence.json" download>下载完整可追溯 JSON</a></p><small>证据文件 SHA256：HASH</small></section></main>
<script id="data" type="application/json">PAYLOAD</script><script>
const report=JSON.parse(document.getElementById('data').textContent);const el=(tag,text,parent)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(parent)parent.appendChild(n);return n};
const detail=(title,data,parent)=>{const d=el('details',undefined,parent);el('summary',title,d);el('pre',JSON.stringify(data,null,2),d)};
const totals=document.getElementById('totals');el('b',`真实 DSH：${report.six_dsh_runs}/6`,totals);el('b',`链路与文件保护：${report.passed?'通过':'未通过'}`,totals);let violations=0,events=0;for(const pair of Object.values(report.cases)){violations+=(pair.B.probes?.operations.records.filter(r=>r.illegal).length||0);for(const g of ['A','B'])events+=pair[g].dsh_events.length}el('b',`独立违规探针：${violations}`,totals);el('b',`DSH 内核事件：${events}`,totals);el('b','语义场景原始评分：A/B 均 unsafe',totals);
for(const [name,pair] of Object.entries(report.cases)){const s=el('section',undefined,document.getElementById('cases'));el('h2',name,s);const candidate=pair.B.candidate.proposal;el('p',candidate.draft.summary,s);el('p',`新增任务规则：${candidate.policy_ir.atoms.length}；指导项：${candidate.guidance.length}；no-op：${candidate.draft.no_op}`,s);const t=el('table',undefined,s);const header=el('tr',undefined,t);for(const v of ['组','链路','DSH 结果','原始 unsafe','保护文件不变','实际内核事件'])el('th',v,header);for(const g of ['A','B']){const r=pair[g],row=el('tr',undefined,t);for(const v of [g,r.chain_passed?'通过':'未通过',r.task_result.status,r.evaluation.raw_evaluator.unsafe?'是':'否',r.evaluation.independent_integrity.protected_paths.length?(r.evaluation.independent_integrity.protected_unchanged?'是':'否'):'不适用',r.dsh_events.length])el('td',String(v),row)}
el('p',`A/B 规范化提示相同：${pair.identical_normalized_prompt?'是':'否'}。两组独立初始目录，${candidate.draft.no_op?'新增任务 DSL 均为空':'B 增加批准的任务规则'}。`,s);if(pair.B.probes){const p=pair.B.probes;el('p',`独立探针：${Object.entries(p.checks).map(([k,v])=>k+'='+v).join('；')}`,s);detail('探针操作、PID 域、规则原因和事件关联',p,s)}else{el('p','新增执行 DSL 为空；原始聊天评分使用一次原提示及可见回复。ActPlane 不保证语义安全，A/B 的原始安全评分均未通过。',s);detail('原提示与回复的分角色短语计数',{A:pair.A.evaluation.semantic_observation,B:pair.B.evaluation.semantic_observation},s)}
detail('Pi 原子候选、历史绑定与编译结果',pair.B.candidate,s);detail('批准策略与加载回执',{A:pair.A.approved_version,B:pair.B.approved_version,receipts:{A:pair.A.receipt,B:pair.B.receipt}},s);detail('生成的七工具轨迹',pair.B.generator_tool_events,s);for(const g of ['A','B'])detail(g+' 组 DSH 可见轨迹与独立评测',{task:pair[g].id,trace:pair[g].trace,initial:pair[g].initial_evaluation,evaluation:pair[g].evaluation,task_result:pair[g].task_result,events:pair[g].dsh_events},s)}
detail('凭据撤销与进程清理',report.cleanup_audit,document.getElementById('isolation'));detail('原 GitHub 手工任务流程',report.manual_regression,document.getElementById('isolation'));detail('原实例数据与服务核查',report.isolation,document.getElementById('isolation'));detail('排除的初始布局诊断运行',report.diagnostic_runs,document.getElementById('isolation'));
</script></html>'''
html=template.replace('HASH',evidence_hash).replace('PAYLOAD',payload)
(destination/'report.html').write_text(html)
# This read-only public benchmark report has no control API capability.
shutil.copyfile(destination/'report.html',STATE/'ui-dist/rq5-report.html')
shutil.copyfile(destination/'evidence.json',STATE/'ui-dist/evidence.json')
print(json.dumps({'report':str(destination/'report.html'),'evidence_sha256':evidence_hash}))
