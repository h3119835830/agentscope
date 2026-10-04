"""Known event coverage limits, separate from compiler acceptance."""
import re

def runtime_limits_for(dsl):
    if not dsl or not re.search(r"\b(?:write|unlink)\s+file\b",dsl):
        return []
    return [{"code":"file_creation_directory_entry",
        "detail":"写入被拒绝时，新建文件可能已留下空目录项。文件内容写入与删除限制不代表所有文件系统元数据变更都已被阻止；完整目录不变性未验收。"}]
def translation_capabilities():
    """Contract of the existing task-domain provider, separate from task intent."""
    return {'backend':'ActPlane','enforcement_scope':'approved task process domain',
        'agent_source':'source AGENT = exec "**" supplied by the task bundle',
        'descendant_domain_inheritance':True,
        'file_events':{'write':'OS file mutation event','unlink':'OS removal/rename event'},
        'event_origin':'All matching processes in the task domain, including children and script interpreters; file events do not depend on which tool initiated the operation.',
        'outside_domain':'Not selected by this task policy; ordinary human processes outside the task domain are unaffected.',
        'semantic_or_content_inspection':False,
        'limits':runtime_limits_for('block write file "/example/**" if AGENT')}
