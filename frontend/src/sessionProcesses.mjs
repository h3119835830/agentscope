export function sessionProcessRow(session){
 const pids=[...new Set((session.process_ids||[]).filter(pid=>Number.isInteger(pid)&&pid>0))];
 const states={running:['运行中','info'],busy:['运行中','info'],idle:['空闲','neutral'],stored:['已保存','neutral'],failed:['失败','bad'],error:['失败','bad'],paused:['已暂停','warn']};
 const state=session.status||(session.running===true?'running':pids.length?'idle':'stored');
 const [label,tone]=states[state]||['状态未知','warn'];
 return {id:session.id,name:session.name?.trim()||'未命名会话',pids,label,tone};
}
