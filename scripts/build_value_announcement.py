#!/usr/bin/env python3
"""Render the maintained announcement into a local, readable product page."""
import hashlib,html,re
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'docs/research/value-reliability-20261012/announcement.md'
TARGET=ROOT/'frontend/public/value-announcement.html'

def inline(text):
 def link(match):
  label,url=match.groups()
  if urlsplit(url).scheme not in ('http','https'):raise ValueError('Unsupported announcement link')
  return '<a href="'+html.escape(url,quote=True)+'" target="_blank" rel="noreferrer">'+html.escape(label)+'</a>'
 pieces=[];start=0
 for match in re.finditer(r'\[([^\]]+)\]\(([^)]+)\)',text):
  pieces.extend((html.escape(text[start:match.start()]),link(match)));start=match.end()
 return ''.join(pieces)+html.escape(text[start:])

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
 .report-link{display:block;background:#eff4fc;border-left:3px solid #83a4d2;padding:16px 18px;text-decoration:none;font-size:13px;line-height:1.8;margin:32px 0;color:#426b9e}
 footer{border-top:1px solid #dfe7f2;padding-top:18px;margin-top:32px;color:#93a0b3;font-size:11px;line-height:1.9;overflow-wrap:anywhere}
 @media(max-width:850px){.layout{grid-template-columns:1fr;gap:0;max-width:760px;padding-top:32px}aside{display:none}h1{font-size:28px}}
 @media(max-width:500px){.topbar{padding:17px 20px}.layout{padding:28px 22px 45px}h1{font-size:25px;line-height:1.6}h2{font-size:19px;margin-top:30px}article p{font-size:13px;line-height:2.1}article>p:first-of-type{font-size:14px}.summary{font-size:11px}.kicker{font-size:10px}}
 @media print{body{background:white}.topbar,aside{display:none}.layout{display:block;max-width:none;padding:0}h1{font-size:25px}article p{font-size:11px}h2{font-size:16px;break-after:avoid}a{color:inherit}}
 '''
 contents=''.join('<a href="#'+i+'">'+html.escape(label)+'</a>' for i,label in toc)
 output='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="announcement-source-sha256" content="'+hashlib.sha256(SOURCE.read_bytes()).hexdigest()+'"><meta name="description" content="通过测试插件、验收保护和数据外发等真实场景，了解 AgentScope 的系统行为保护。"><title>'+html.escape(title)+' · AgentScope</title><style>'+css+'</style></head><body><div class="topbar"><a class="brand" href="/?view=overview">◈ AgentScope</a><a href="/?view=overview">← 返回总览</a></div><main class="layout"><aside aria-label="文章目录"><p>本文内容</p>'+contents+'</aside><article><div class="kicker">产品公告 · 2026.10.12</div><h1>'+html.escape(title)+'</h1><div class="summary">六类场景 · 72 次执行对照 · 真实 DSH 任务补充<br>从工具入口走到实际系统行为，看清已验证的价值与适用边界。</div>'+''.join(blocks)+'<a class="report-link" href="/value-evidence.html">查看六项本机实验报告 →</a><footer>本页介绍历史实验与部署条件；当前 Agent 的保护状态请查看总览的实时核验。配置与扩权仍需人工确认。</footer></article></main></body></html>'
 TARGET.parent.mkdir(parents=True,exist_ok=True);TARGET.write_text(output)
 print('Generated '+str(TARGET))

if __name__=='__main__':main()
