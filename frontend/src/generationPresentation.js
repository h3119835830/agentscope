export const states={queued:'排队中',running:'生成中',completed:'生成完成',ready:'候选已生成',partial:'部分失败',failed:'失败',cancelled:'已取消',interrupted:'已中断',approved:'已通过候选',pending_review:'待审核',rejected:'已拒绝',complete:'二审完整',description:'描述性内容',unreviewed:'未二审',needs_clarification:'待澄清',needs_adaptation:'需本机适配',required:'需本机适配',complete_adaptation:'已适配',not_required:'无需适配',compiled:'已编译',requires_context:'需本机适配',unsupported:'指导项 / 无执行 DSL',compile_failed:'编译失败',compile_timeout:'编译超时',backend_missing:'编译器不可用',invalid_candidate:'规则校验失败'};
export const phases={source:'采集并固定来源',single_review:'完整性二审',completeness_review:'完整性二审',extract_and_review:'策略抽取与完整性二审',ir_and_compile:'产物生成与编译',review:'人工审核'};
export const levels={semantic_only:'语义规则',content:'内容规则',per_event:'单事件规则',cross_event:'跨事件规则',not_applicable:'不适用'};
export const scopes={self_contained:'通用',project:'项目 / 仓库',task:'任务',not_applicable:'不适用'};
export const short=value=>value?.slice(0,12)||'—';
export const time=value=>value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'—';
export const sourceName=run=>run?.source?.repository?.startsWith('manual/')?'手工策略输入':run?.source?.repository||run?.input?.repo_url||(run?.input?.statement_version_id?'单条策略二审 / 生成':'未指定来源');
export const initialFilters=()=>({q:'',execution_level:'',context_scope:'',completeness:'',adaptation:'',loadable:''});
