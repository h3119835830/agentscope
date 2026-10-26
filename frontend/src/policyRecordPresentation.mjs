export const operationLabel=value=>({open:'打开文件',read:'读取',write:'写入',unlink:'删除',exec:'执行程序',connect:'连接'})[value]||value;
export const effectLabel=value=>({block:'阻止并反馈',notify:'记录并提醒',kill:'终止违规进程'})[value]||value;
export const policyAction=value=>({block:'阻断',kill:'终止',allow:'允许',observe:'记录',notify:'通知',report:'上报',mixed:'多种动作'})[value]||'未记录';
export function clauseAction(clauses=[]){const values=[...new Set(clauses.map(c=>c.effect).filter(Boolean))];return values.length===1?values[0]:values.length?'mixed':null;}
