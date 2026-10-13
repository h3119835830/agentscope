#!/usr/bin/env python3
"""Render the maintained announcement into a local, readable product page."""
import hashlib,html,re
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'docs/research/value-reliability-20261012/announcement.md'
TARGETS=[ROOT/'frontend/public'/name for name in ('value-announcement.html','value-evidence.html')]

def inline(text):
 def plain(value):
  return re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',html.escape(value))
 def link(match):
  label,url=match.groups()
  if urlsplit(url).scheme not in ('http','https'):raise ValueError('Unsupported announcement link')
  return '<a href="'+html.escape(url,quote=True)+'" target="_blank" rel="noreferrer">'+html.escape(label)+'</a>'
 pieces=[];start=0
 for match in re.finditer(r'\[([^\]]+)\]\(([^)]+)\)',text):
  pieces.extend((plain(text[start:match.start()]),link(match)));start=match.end()
 return ''.join(pieces)+plain(text[start:])

def main():
 text=SOURCE.read_text();blocks=[];toc=[];title=None
 for paragraph in text.strip().split('\n\n'):
  if paragraph.startswith('# '):
   assert title is None;title=paragraph[2:];continue
  if paragraph.startswith('## '):
   label=paragraph[3:];ident='section-'+str(len(toc)+1);toc.append((ident,label))
   blocks.append('<h2 id="'+ident+'">'+inline(label)+'</h2>')
  else:blocks.append('<p>'+inline(paragraph.replace('\n',' '))+'</p>')
 assert title and toc
 figure='''<figure class="observation-figure" aria-label="应用记录与内核侧约束的观察层次示意"><div class="observation-lane"><span class="lane-label">应用层任务记录</span><div class="lane-steps"><span>启动任务</span><i aria-hidden="true">→</i><span>生成报告</span><i aria-hidden="true">→</i><span>返回结果</span></div></div><div class="observation-lane kernel"><span class="lane-label">内核侧关键操作</span><div class="lane-steps"><span>进程访问文件或网络</span><i aria-hidden="true">→</i><span>规则检查与处置</span><i aria-hidden="true">→</i><span>命中事件与执行返回</span></div></div><figcaption>同一任务的两种观察层次 · 机制示意</figcaption></figure>'''
 assert len(blocks)>2 and blocks[0].startswith('<p>') and blocks[1].startswith('<p>')
 blocks.insert(2,figure)
 css='''
 :root{color-scheme:light;font-family:Inter,"Microsoft YaHei",system-ui,sans-serif;color:#324963;background:#f7f9fc}
 *{box-sizing:border-box}body{margin:0}a{color:#426da8;text-underline-offset:4px}a:hover{color:#244d87}
 .topbar{max-width:1120px;margin:auto;padding:22px 28px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #e2e8f1;font-size:12px}
 .topbar a{text-decoration:none}.brand{font-weight:650;letter-spacing:.3px;color:#355a8a}
 .layout{max-width:1120px;margin:0 auto;display:grid;grid-template-columns:230px minmax(0,1fr);gap:56px;padding:48px 28px 70px}
 aside{position:sticky;top:35px;align-self:start;font-size:12px;line-height:1.85;padding-top:6px}aside>p{color:#94a2b6;font-size:10px;letter-spacing:1px;margin:0 0 16px}
 aside a{display:block;text-decoration:none;color:#8191a7;margin:0 0 14px;padding-left:12px;border-left:1px solid #dde5ef}aside a:hover{color:#426da8;border-color:#7295c5}
 article{min-width:0}.kicker{font-size:11px;letter-spacing:.8px;color:#8496b0;margin:0 0 14px}h1{font-size:32px;line-height:1.5;letter-spacing:-.8px;color:#213b5b;margin:0 0 20px;font-weight:650}
 .summary{margin:0 0 32px;padding:15px 0;border-top:1px solid #e2e8f1;border-bottom:1px solid #e2e8f1;color:#6380a6;font-size:12px;line-height:1.9}
 article p{font-size:14px;line-height:2.05;color:#657891;margin:0 0 18px}article>p:first-of-type{font-size:16px;color:#415e80;line-height:2}
 h2{font-size:21px;font-weight:600;line-height:1.65;color:#304f75;margin:38px 0 16px;scroll-margin-top:25px;letter-spacing:-.3px}
 article strong{color:#375a85;font-weight:600}
 .observation-figure{margin:28px 0 34px;border:1px solid #dfe7f3;border-radius:8px;overflow:hidden;background:#fff}
 .observation-lane{padding:17px 19px;border-bottom:1px solid #e5ebf4}.observation-lane.kernel{background:#eff4fc}
 .lane-label{display:block;font-size:11px;color:#7d91ad;margin-bottom:11px}.kernel .lane-label{color:#5277aa}
 .lane-steps{display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:12px;color:#5d7697;line-height:1.8}.lane-steps>span{flex:1}.lane-steps>i{font-style:normal;color:#a5b6ce;font-size:14px;flex-shrink:0}
 figcaption{font-size:10px;color:#97a5b8;padding:10px 19px;background:#fafbfd}
 footer{border-top:1px solid #dfe7f2;padding-top:18px;margin-top:32px;color:#93a0b3;font-size:11px;line-height:1.9;overflow-wrap:anywhere}
 @media(max-width:850px){.layout{grid-template-columns:1fr;gap:0;max-width:760px;padding-top:32px}aside{display:none}h1{font-size:28px}}
 @media(max-width:500px){.topbar{padding:17px 20px}.layout{padding:28px 22px 45px}h1{font-size:25px;line-height:1.6}h2{font-size:19px;margin-top:30px}article p{font-size:13px;line-height:2.1}article>p:first-of-type{font-size:14px}.summary{font-size:11px}.kicker{font-size:10px}.observation-lane{padding:14px}.lane-steps{font-size:11px;gap:7px}.lane-steps>span{overflow-wrap:anywhere}.lane-steps>i{font-size:12px}figcaption{padding:9px 14px}}
 @media print{body{background:white}.topbar,aside{display:none}.layout{display:block;max-width:none;padding:0}h1{font-size:25px}article p{font-size:11px}h2{font-size:16px;break-after:avoid}a{color:inherit}}
 '''
 contents=''.join('<a href="#'+i+'">'+html.escape(label)+'</a>' for i,label in toc)
 output='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="announcement-source-sha256" content="'+hashlib.sha256(SOURCE.read_bytes()).hexdigest()+'"><meta name="description" content="从插件读取凭证、后台进程、文件越界和跨进程数据流转等场景，理解内核侧可审计、可反馈、可监控的执行约束。"><title>'+html.escape(title)+' · AgentScope</title><style>'+css+'</style></head><body><div class="topbar"><a class="brand" href="/?view=overview">◈ AgentScope</a><a href="/?view=overview">← 返回总览</a></div><main class="layout"><aside aria-label="文章目录"><p>本文内容</p>'+contents+'</aside><article><div class="kicker">产品公告 · 更新于 2026.10.13</div><h1>'+html.escape(title)+'</h1><div class="summary">看见应用日志遗漏的行为，关联跨进程风险。<br>让内核侧的策略执行可审计、可反馈、可监控。</div>'+''.join(blocks)+'<footer>研究依据见文中论文与源码链接。</footer></article></main></body></html>'
 for target in TARGETS:
  target.parent.mkdir(parents=True,exist_ok=True);target.write_text(output)
  print('Generated '+str(target))

if __name__=='__main__':main()
