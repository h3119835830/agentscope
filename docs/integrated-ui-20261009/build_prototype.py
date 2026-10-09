"""Compose the accepted rule editor and catalogue with the integrated UI shell."""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent


def build():
    base = (DOCS / "session-security-design-20261008/prototype.template.html").read_text(encoding="utf-8")
    styles = re.search(r"<style>(.*?)</style>", base, re.S).group(1)
    script = re.findall(r"<script>(.*?)</script>", base, re.S)[0]
    prefix = script[:script.index("function selectedRules()")]
    prefix = prefix.replace("const taskDraft=", "let taskDraft=").replace("let page='session'", "let page='overview'")
    names = ["selectedRules", "capability", "ruleTable", "renderPlatform", "openRuleDetails", "evidenceHtml", "preview", "openEditor", "editorValue", "closeDialog", "inspect"]
    shared = []
    for name in names:
        if name == "selectedRules":
            shared.append("function selectedRules(){return policyRulesForScope(domain); }\n")
            continue
        start = re.search(r"^function " + name + r"\(", script, re.M).start()
        end = re.search(r"^(?:function |document\.addEventListener|for\(const id)", script[start + 1:], re.M)
        shared.append(script[start:start + 1 + end.start()] if end else script[start:])
    submit = re.search(r"^document\.addEventListener\('submit'.*$", script, re.M).group(0)
    app = "\n".join((HERE / name).read_text(encoding="utf-8") for name in ["session-model.js", "session-controller.js", "session-views.js", "app.js"])
    extra_styles = (HERE / "integrated.css").read_text(encoding="utf-8")
    catalogue = json.loads((DOCS / "session-security-design-20261008/policy-catalogue.json").read_text(encoding="utf-8"))
    data = json.dumps(catalogue, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    html = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AgentScope · 合并界面原型</title><style>{styles}\n{extra_styles}</style></head><body>
<div class="shell"><aside class="sidebar"><div class="brand"><div class="logo">A</div><div>AgentScope</div></div>
<nav aria-label="平台导航">{''.join(f'<button class="nav" data-page="{key}"><span aria-hidden="true">{icon}</span> {label}<span data-count="{key}"></span></button>' for key, icon, label in [('overview','▦','总览'),('sessions','◈','会话'),('approvals','⇥','审批'),('library','▤','策略库'),('system','⌁','系统')])}</nav></aside>
<main class="main"><header class="topbar"><div class="context" id="context"></div><div class="page-actions"><span class="badge amber">样例 · 未连接运行时</span><div id="page-actions"></div></div></header><div class="content" id="content"></div></main></div>
<dialog id="editor" aria-labelledby="editor-title"></dialog><dialog id="inspector" aria-labelledby="inspector-title"></dialog><div id="toast" class="toast" role="status" hidden></div>
<script id="catalogue-data" type="application/json">{data}</script>
<script>{prefix}\n{''.join(shared)}\n{app}\n{submit}
for(const id of ['editor','inspector'])document.getElementById(id).addEventListener('cancel',()=>{{if(lastOpener?.isConnected)lastOpener.focus()}});
render();
</script></body></html>'''
    target = DOCS / "prototype/AgentScope-合并界面原型.html"
    target.write_text(html, encoding="utf-8")
    print(json.dumps({"html": str(target), "templates": len(catalogue["templates"]), "runtime_connected": False}, ensure_ascii=False))


if __name__ == "__main__":
    build()
