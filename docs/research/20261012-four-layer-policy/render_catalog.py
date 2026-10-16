"""Render the case audit from reviewed annotations and fixed source evidence."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def render():
    notes=json.loads((ROOT/'case-notes.json').read_text());index=json.loads((ROOT/'example-source-index.json').read_text());evidence=json.loads((ROOT/'source-evidence.json').read_text())
    doc=next(e for e in evidence if e['repo']=='actplane-master' and e['path']=='docs/rule-language.md')
    headings={e['name'].split(' — ')[0].replace('### ',''):e['line'] for e in doc['symbols'] if e['name'].startswith('### E')}
    assert {e['id'] for e in index['document_examples']}=={e['id'] for e in notes['cases']}
    test_names={e['name'] for e in index['test_cases']};cases=[]
    for case in notes['cases']:
        assert set(case['upstream_tests'])<=test_names
        cases.append({**case,'source_url':doc['url']+'#L'+str(headings[case['id']]),'source_file_sha256':doc['sha256']})
    catalog={**notes,'cases':cases}
    lines=['# 可复用案例及证据边界','','2026-10-12。全量核对 E1–E13；本轮只做源码/夹具审计，未运行案例。分类描述配方复用成本，不表示已完成 DSH 验收。机器可读详表见 [case-catalog.json](case-catalog.json)，基准来源见 [benchmark-catalog.json](benchmark-catalog.json)。','','## 1. 13 个文档示例与 12 个夹具','','当前 test/e2e_cases.yaml 有 12 个 case：E8 合并在 E1，另有 E5b；E13 没有独立 case。driver 使用重命名 bash/true 替身，按 NDJSON 匹配计数判定，不能证明真实 git、人工确认、脱敏或多会话隔离。文档中的 block 与夹具中的 kill 也应分别核对。','','| 例子 | 适用范围 | 文档 / 夹具 | 复用分类 | 关键差距 |','|---|---|---|---|---|']
    scope={'system':'系统','agent':'Agent','workspace':'工作区','session':'会话','delegation':'子委托'}
    for c in cases:
        lines.append('| ['+c['id']+' '+c['name']+']('+c['source_url']+') | '+'、'.join(scope[x] for x in c['scope'])+' | '+c['document_effect']+' / '+c['test_effect']+' | '+c['classification']+' | '+c['risk']+' |')
    lines+=['','“可参数化复用”仍需真实主体/路径绑定、编译支持核验和人工确认；没有无条件直接应用的模板。示例配方随仓库 MIT，内核文件按各自 SPDX；基准材料按原来源许可核对，本附件只保存索引、原创摘要和摘要值。','','## 2. 每例正反控制与适配要求','']
    for c in cases:
        lines+=['### '+c['id']+' '+c['name'],'','工具层盲区：'+c['tool_blind_spot'],'','允许对照：'+c['expected_allow'],'','拒绝断言：'+c['expected_deny'],'','适配：'+c['adaptation'],'']
    b=json.loads((ROOT/'benchmark-catalog.json').read_text());lines+=['## 3. 其他可用语料与任务','','| 来源 | 代表项 | 可借鉴部分 | 不能直接外推 |','|---|---|---|---|']
    for family in b['families']:
        lines.append('| '+family['id']+' '+family['name']+' | '+'、'.join(family['representatives'])+' | '+family['expected_effect']+' | '+family['risk']+' |')
    lines+=['','每个 benchmark 的固定来源、许可核对、依赖和工具层盲区在 benchmark-catalog.json。RQ1 原仓库文档、benchmark 数据、服务与镜像的许可不能统一写成 ActPlane MIT。','','## 4. 优先复现顺序','','八类为 E7（结合 E1）、E2、E4、E5、E6、E11、E12、E13。先解决作用域与审批，再验证跨事件语义，最后接入完整任务效用对照。使用合成秘密、独立本地服务和临时仓库，不对真实业务对象操作。具体步骤和验收证据见 [reproduction-plan.md](reproduction-plan.md)。','']
    return '\n'.join(lines),catalog
if __name__=='__main__':
    text,catalog=render()
    (ROOT/'case-catalog.md').write_text(text)
    (ROOT/'case-catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n')
