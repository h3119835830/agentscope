export const effects = {
  block: {name:'阻断操作', detail:'在支持的拦截点拒绝操作。', icon:'⊘'},
  notify: {name:'记录通知', detail:'记录匹配事件，允许操作继续。', icon:'♧'},
  kill: {name:'终止进程', detail:'终止命中进程，可能中断任务；不等同于事前阻断。', icon:'×'},
};
export const modes={suffix:'文件后缀',filename:'文件名',tail:'路径后缀',directory:'目录及内容',exact:'完整路径',exec:'可执行程序',endpoint:'IPv4 地址 / 前缀',flow:'敏感来源 → 网络',remote:'网络来源 → 执行'};
export const operations={open:'打开',write:'写入',unlink:'删除',exec:'执行',connect:'连接'};
export const lines=value=>value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
export function validate(p){
 if(!p.name.trim())return '请填写策略名称。';
 if(!Object.hasOwn(effects,p.effect))return '请选择支持的处置动作。';
 if(!Object.hasOwn(modes,p.mode))return '请选择匹配方式。';
 const values=lines(p.values);if(!values.length)return '请填写保护对象。';
 if(values.length>16)return '单项策略最多配置 16 个匹配对象。';
 if(!p.ops.length||p.ops.some(o=>!Object.hasOwn(operations,o)))return '至少选择一项触发操作。';
 const permitted=['exec','remote'].includes(p.mode)?['exec']:['endpoint','flow'].includes(p.mode)?['connect']:['open','write','unlink'];
 if(p.ops.some(op=>!permitted.includes(op)))return '触发操作与匹配对象不一致，请重新选择。';
 if(!p.reason.trim())return '请填写命中后的反馈。';
 if(/[\u0000-\u001f"\\]/.test(p.reason))return '反馈请使用单段文字，避免英文双引号和反斜杠。';
 for(const value of values){
  if(['suffix','flow','filename','tail'].includes(p.mode)&&new TextEncoder().encode((['filename','tail'].includes(p.mode)?'/':'')+value).length>63)return '文件或路径后缀最多 63 字节。';
  if(/[\u0000-\u001f"\\]/.test(value))return '匹配对象不能包含控制字符、引号或反斜杠。';
  if(['suffix','flow'].includes(p.mode)&&(!value.startsWith('.')||/[/*?]/.test(value)||value.length<2))return '后缀应为 .env 这样的字面值，无需填写通配符或目录。';
  if(p.mode==='filename'&&/[/*?]/.test(value))return '文件名只填写名称，例如 .env 或 AGENTS.md。';
  if(p.mode==='tail'&&(value.startsWith('/')||/[?*]/.test(value)||value.split('/').includes('..')))return '路径后缀不能以 / 开头或包含通配符、..。';
  if(['directory','exact'].includes(p.mode)&&(!value.startsWith('/')||/[?*]/.test(value)||value.split('/').includes('..')))return '请填写实际绝对路径，无需添加通配符。';
  if(['exec','remote'].includes(p.mode)&&value!=='*'&&!/^[\w./-]+$/.test(value))return '程序填写可执行名或完整路径，不能填写命令行参数。';
  if(p.mode==='endpoint'&&value!=='*'){
   const partial=value.endsWith('.'),parts=value.replace(/\.$/,'').split('.');
   if(parts.length<(partial?1:4)||parts.length>(partial?3:4)||parts.some(x=>!/^\d{1,3}$/.test(x)||+x>255))return '填写 IPv4 地址（如 10.0.0.8）或地址前缀（如 10.0.0.）。';
  }
 }
 return '';
}
export function patterns(p){return lines(p.values).flatMap(v=>p.mode==='suffix'||p.mode==='flow'?['**/*'+v]:p.mode==='filename'||p.mode==='tail'?['**/'+v]:p.mode==='directory'?[v==='/'?'/':v.replace(/\/$/,''),v.replace(/\/$/,'')+'/**']:[v]);}
export function ruleDsl(p){
 const error=validate(p);if(error)throw Error(error);
 const targets=patterns(p),rows=[];
 if(p.mode==='flow')targets.forEach(t=>rows.push('source SENSITIVE = file '+JSON.stringify(t)));
 if(p.mode==='remote')rows.push('source REMOTE = endpoint "*"');
 rows.push('rule system-'+p.id.replace(/[^a-z0-9_-]/g,'-')+':');
 for(const op of p.ops){
  const kind=op==='exec'?'':op==='connect'?'endpoint ':'file ';
  for(const t of (p.mode==='flow'?['*']:targets))rows.push('  '+p.effect+' '+op+' '+kind+JSON.stringify(t)+' if AGENT'+(p.mode==='flow'?' and SENSITIVE':p.mode==='remote'?' and REMOTE':''));
 }
 rows.push('  because '+JSON.stringify(p.reason));return rows.join('\n');
}
export function matches(p,path){
 const value=path.trim();if(!value||!value.startsWith('/')||value.split('/').some(x=>x==='..'||x==='.'))return null;
 const values=lines(p.values);return values.some(v=>['suffix','flow'].includes(p.mode)?value.endsWith(v):['filename','tail'].includes(p.mode)?value.endsWith('/'+v):p.mode==='directory'?value===v.replace(/\/$/,'')||value.startsWith(v.replace(/\/$/,'')+'/'):p.mode==='exact'?value===v:false);
}
