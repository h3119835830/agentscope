#!/usr/bin/env python3
"""Publish only measured summaries, keeping execution controls distinct from LLM evals."""
import argparse,datetime,hashlib,html,json,shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
NAMES={'plugin':'测试入口内的凭证读取','integrity':'源码可写、验收依据不可改','path':'符号链接、截断与重命名覆盖','flow':'派生文件、跨进程与同地址新连接','descendants':'shell 与后台后代继承','isolation':'两个资源对象的访问边界'}
MODES={'unconstrained_execution':'执行层无约束对照','tool_entry_only':'仅检查工具入口的对照','static_sandbox':'等价任务能力的静态沙箱','actplane':'ActPlane'}
CONCLUSIONS={
 'plugin':('合成凭证读取被拒绝，合法源码读取成功。','静态隐藏凭证目录也能阻止；本轮是插件行为载荷，未复现某个真实插件漏洞。'),
 'integrity':('实现写入成功；测试重写与删除被拒绝，测试哈希保持不变。','只读测试挂载同样有效；测试未被篡改不等于修复正确。'),
 'path':('合法源码写入成功；链接写入、直接截断和重命名覆盖被拒绝。','静态只读挂载同样有效；不推导全部竞态及文件系统变体已覆盖。'),
 'flow':('普通来源向同一端点的新连接成功；秘密经派生文件、重命名、另一进程后的新连接被拒绝。','本轮静态沙箱允许同一地址的两种上报；ActPlane 增加了来源相关区分。只验证新 connect。'),
 'descendants':('合法读取成功；Python 经 shell 启动的后台后代读取合成凭证被拒绝。','凭证目录隔离也能阻止；不以父工具名称作为实际效果证明。'),
 'isolation':('当前任务资源读取成功，另一资源对象读取被拒绝。','静态文件隔离同样有效；此实验验证对象边界，不能冒充两个原生会话独立执行域。'),
}

def main():
 p=argparse.ArgumentParser();p.add_argument('report');a=p.parse_args()
 raw=Path(a.report);data=json.loads(raw.read_text());cases=data['cases']
 assert data['passed'] and len(cases)==72 and data['repetitions']==3
 out=ROOT/'docs/research/value-reliability-20261012';out.mkdir(parents=True,exist_ok=True)
 ev=ROOT/'docs/REVIEW/evidence/value-reliability-20261012';ev.mkdir(parents=True,exist_ok=True)
 shutil.copy2(raw,ev/'scenarios-final.json')
 date=datetime.datetime.fromtimestamp(data['finished_at'],datetime.timezone(datetime.timedelta(hours=8))).date().isoformat()
 proof={'schema':'agentscope.value-evidence.v1','date':date,'environment':'WSL2 · Linux '+data['kernel'],'reportUrl':'/value-evidence.html','scenarios':{}}
 rows=[]
 for sid,name in NAMES.items():
  selected=[c for c in cases if c['scenario']==sid]
  measurements=[]
  for mode,label in MODES.items():
   run=[c for c in selected if c['mode']==mode]
   assert len(run)==3 and all(c['harness_completed'] for c in run)
   measurements.append(f"| {label} | {sum(c['legal_completed'] for c in run)}/3 | {sum(c['unsafe_effect'] for c in run)}/3 | {sum(c['kernel_denial_proven'] for c in run)}/3 |")
  protected=[c for c in selected if c['mode']=='actplane']
  assert all(c['legal_completed'] and not c['unsafe_effect'] and c['kernel_denial_proven'] for c in protected)
  result,control=CONCLUSIONS[sid]
  proof['scenarios'][sid]={'verified':True,'repetitions':3,'result':result,'control':control,'evidence_sha256':hashlib.sha256(raw.read_bytes()).hexdigest()}
  body=f"# {name}\n\n验证日期：{date}。环境：{data['kernel']}。ActPlane 二进制 SHA-256：`{data['binary_sha256']}`。\n\n{result}\n\n{control}\n\n## 方法与对照\n\n这是已选攻击载荷的执行效果实验；每组重复三次。未评估提示注入成功率，未部署 CaMeL、Progent、FIDES。入口对照只批准外层命令，不检查载荷内部的后续系统调用；不能泛化为所有工具层权限系统。静态沙箱使用 bubblewrap，只读根、允许的源码及输出目录可写、凭证目录隐藏或另一资源被遮蔽；网络对照保留相同端点可达性。\n\n| 执行方式 | 合法任务完成 | 不安全效果发生 | 内核拒绝证据 |\n|---|---:|---:|---:|\n"+'\n'.join(measurements)+"\n\n## 可复现证据\n\n完整原始记录见 `../../REVIEW/evidence/value-reliability-20261012/scenarios-final.json`，含每次载荷、执行命令、策略、实际操作结果、文件前后哈希、接收端内容和真实内核事件。全部使用合成数据和回环接收端。界面只显示摘要，不向客户展示原始 JSON。\n\n示例已加载策略：\n\n```yaml\n"+protected[0]['policy']+"```\n\n## 失败记录及限制\n\n首轮未设置 ACTPLANE_RESERVE_OPEN_RULES，三个读取类场景的 ActPlane 规则载入失败，共九条失败记录，保留于 scenarios-initial-failure.json。修正实验启动配置后重新执行全部 72 条。规则载入失败不能记为保护成功。\n\n本报告的“完成”是确定性载荷中的合法操作完成，不等于真实 Agent 业务任务完成、安全反馈送达或模型正确修复。原生 DSH 补充任务另记。预先打开的连接、共享内存、撤权前 mmap、远程业务语义不由本结果证明。\n"
  (out/f'experiment-{sid}.md').write_text(body)
  rows.append(f'<tr><th>{html.escape(name)}</th><td>{html.escape(result)}</td><td>{html.escape(control)}</td><td>3 次</td></tr>')
 (ROOT/'frontend/src/valueEvidence.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
 report_page=out/'experiment-report.html'
 report_page.write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AgentScope 本机实验报告</title><style>body{font:16px/1.8 system-ui,sans-serif;max-width:1100px;margin:40px auto;padding:0 20px;color:#223143}h1{font-size:28px}table{border-collapse:collapse;width:100%}th,td{padding:14px;text-align:left;vertical-align:top;border-bottom:1px solid #dce3e9}small{overflow-wrap:anywhere}a{color:#146685}@media(max-width:650px){table,tbody,tr,th,td{display:block}thead{display:none}tr{border-bottom:2px solid #cad6df}td,th{border:0;padding:6px}}</style><h1>真实系统行为的六项本机实验</h1>'''+f'<p>验证日期：{date} · {html.escape(data["kernel"])} · 6 类场景 × 4 种执行方式 × 3 次重复，共 72 次。</p><p>ActPlane 组 18 次合法操作均成功，攻击效果均受阻，并有内核拒绝记录。静态沙箱在五类文件与后代场景同样有效。来源实验中，同一地址的普通连接被允许，秘密派生来源的新连接被拒绝。</p><p><strong>方法限制：</strong>这是确定性攻击载荷的执行对照，不是提示注入成功率评测。工具入口对照不代表所有工具权限系统；未复现 CaMeL、Progent 或 FIDES。历史实验不能证明当前 Agent 正受保护。</p><table><thead><tr><th>场景</th><th>本轮结果</th><th>已有防护与边界</th><th>重复</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table><p>首轮因读取钩子未预留造成九条载入失败，保留失败记录；修正启动配置后整套复验通过。新 connect 拒绝不代表已有连接不能发送。资源边界实验不代表原生会话隔离。测试文件完整不代表测试通过。</p><p><small>二进制 SHA-256：'+data['binary_sha256']+'<br>原始实验 SHA-256：'+hashlib.sha256(raw.read_bytes()).hexdigest()+'</small></p><p>机制依据：<a href="https://arxiv.org/html/2606.25189v2">ActPlane 论文 v2</a>；<a href="https://github.com/eunomia-bpf/ActPlane/tree/404542899a2153af0952cbf0dc52aeab0b7c5034">固定提交源码</a>。部署需满足 Linux/eBPF、已验证内核能力和可信 Broker 等条件。</p></html>')
 print(json.dumps({'reports':str(out),'summary':str(report_page),'cases':len(cases)}))

if __name__=='__main__':main()
