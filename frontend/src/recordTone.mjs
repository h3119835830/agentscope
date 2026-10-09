// Display semantics only. A color never supplies missing runtime evidence.
const tones={
  good:['已连接','已核验','已完成','工具已返回','已应用并核验','实际保护已核验'],
  info:['执行受控','已加载','已编译','已发现进程','入口已登记','已登记','执行中','允许执行','已通过候选','已批准'],
  warn:['执行暂停','已暂停','已加载，执行暂停','待启动核验','待核验','当前未核验','未核验','证据已过期','状态未知','待确认策略','待审核','待生成策略','策略生成中','恢复中','正在启动','等待用户确认','校验收紧','仅观测'],
  bad:['失败','启动失败','保护核验失败','策略应用失败','加载失败','编译失败','工具返回失败','工具被拒绝','已拒绝'],
  purple:['行为约定','实例共享策略'],
};
export function recordTone(label){
  return Object.entries(tones).find(([,labels])=>labels.includes(label))?.[0]||'neutral';
}
