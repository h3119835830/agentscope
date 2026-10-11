"""Known event coverage limits, separate from compiler acceptance."""
import re

def runtime_limits_for(dsl):
    if not dsl or not re.search(r"\b(?:write|unlink)\s+file\b",dsl):
        return []
    return [{"code":"file_creation_directory_entry",
        "detail":"写入被拒绝时，新建文件可能已留下空目录项。文件内容写入与删除限制不代表所有文件系统元数据变更都已被阻止；完整目录不变性未验收。"}]
def translation_capabilities(*,agent_source=None):
    """Contract of the existing task-domain provider, separate from task intent."""
    value = {'backend':'ActPlane','enforcement_scope':'approved task process domain',
        'agent_source':'source AGENT = exec "**" supplied by the task bundle',
        'descendant_domain_inheritance':True,
        'file_events':{'write':'OS file mutation event','unlink':'OS removal/rename event'},
        'event_origin':'All matching processes in the task domain, including children and script interpreters; file events do not depend on which tool initiated the operation.',
        'outside_domain':'Not selected by this task policy; ordinary human processes outside the task domain are unaffected.',
        'semantic_or_content_inspection':False,
        'classification_contract':{
            'semantic_only':'Meaning, correctness, politeness or qualitative judgment that cannot be determined at OS events.',
            'content':'Requires inspecting or validating document/output contents.',
            'per_event':'An OS file access/mutation, execution or network event restriction. Missing concrete paths or machine parameters affect context/adaptation, not this classification.',
            'cross_event':'An execution constraint gated by prior events or lineage, where the supplied compiler grammar supports that gate.',
            'not_applicable':'Description or reference rather than an instruction for the current agent.'},
        'limits':runtime_limits_for('block write file "/example/**" if AGENT')}

    if agent_source:
        value.update(enforcement_scope='approved registered Agent process domain',
            agent_source='source AGENT = exec '+repr(agent_source)+' from the verified Agent process executable',
            file_events={'open':'BPF-LSM file_open access decision', 'read':'BPF-LSM file_permission read access decision',
                         'write':'BPF-LSM file mutation access decision', 'unlink':'OS removal/rename event'},
            candidate_validation='ActPlane AST and static backend compilation first; Broker pinned-runtime capability validation again before manual application',
            feedback={'policy_reason':'The DSL because clause records the policy explanation.',
                      'delivery':'User-facing feedback delivery is a separate tool/runtime receipt, not guaranteed by static compilation.'})
    return value


def generation_capabilities(context):
    if context.get('kind')=='agent':
        return context['environment_binding']['values']['capabilities']
    return translation_capabilities()
