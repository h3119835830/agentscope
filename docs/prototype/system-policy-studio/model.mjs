export const effects = {
  block: {name:'阻断操作', detail:'在支持的拦截点拒绝操作。', icon:'⊘'},
  notify: {name:'记录通知', detail:'记录匹配事件，允许操作继续。', icon:'♧'},
  kill: {name:'终止进程', detail:'终止命中进程，可能中断任务；不等同于事前阻断。', icon:'×'},
};
export const modes={suffix:'文件后缀',filename:'文件名',tail:'路径后缀',directory:'目录及内容',exact:'完整路径',exec:'可执行程序',endpoint:'IPv4 地址 / 前缀',flow:'敏感来源 → 网络',remote:'网络来源 → 执行'};
export const operations={open:'打开',write:'写入',unlink:'删除',exec:'执行',connect:'连接'};
const corpus='https://github.com/eunomia-bpf/ActPlane/blob/63db86945c9b8618a46aa68c8de214bc4b8343d9/docs/corpus/candidate_rules.tsv';
const language='https://github.com/eunomia-bpf/ActPlane/blob/master/docs/rule-language.md';
const base=(id,name,category,description,mode,values,ops,effect,reason,origin,source,extra={})=>({id,name,category,description,mode,values,ops,effect,reason,origin,source,configured:false,...extra});
export const catalog=[
 base('env','环境凭据文件','凭据保护','保护所有以 .env 结尾的文件','suffix','.env',['open'],'block','该文件可能含有凭据。请使用脱敏配置或受控凭据接口。','RQ1 · 秘密配置约束提炼',corpus+'#L80',{recommended:true}),
 base('ssh','SSH 私钥','凭据保护','保护常见 SSH 私钥文件','tail','.ssh/id_rsa\n.ssh/id_ed25519\n.ssh/id_ecdsa',['open'],'block','请通过获准的 SSH 代理使用凭据，勿直接打开私钥。','平台扩展 · 私钥访问约束',language),
 base('cloud','云服务凭据','凭据保护','保护 AWS 与 Kubernetes 凭据配置','tail','.aws/credentials\n.kube/config',['open'],'block','请使用受控云服务接口，或申请此凭据的特定访问权限。','平台扩展 · 凭据文件约束',language),
 base('system-files','系统身份与授权文件','文件保护','保护系统账号和提权配置','exact','/etc/passwd\n/etc/shadow\n/etc/sudoers',['write','unlink'],'block','系统账号与授权配置由管理员维护，请提交变更申请。','平台扩展 · Linux 主机边界',language,{recommended:true}),
 base('policy-store','安全策略文件','文件保护','保护策略源文件与配置目录','directory','',['write','unlink'],'block','请通过策略配置与人工确认流程变更安全策略。','平台设计 · 安全配置保护',language,{recommended:true,placeholder:'/实际策略目录'}),
 base('audit-store','审计记录','文件保护','防止 Agent 修改或删除审计资料','directory','',['write','unlink'],'block','审计记录由平台维护，Agent 不应修改或删除。','平台设计 · 审计完整性',language,{recommended:true,placeholder:'/实际审计目录'}),
 base('privilege','提权程序','进程与网络','限制通过 sudo、su 执行提权','exec','sudo\nsu',['exec'],'block','当前 Agent 不应自行提权，请申请受控的管理员操作。','平台扩展 · 最小权限边界',language,{recommended:true}),
 base('network-audit','网络连接审计','进程与网络','记录 Agent 及子进程的 IPv4 连接','endpoint','*',['connect'],'notify','检测到网络连接，请确认目标符合任务需要。','ActPlane · connect / notify',language,{note:'覆盖 IPv4 连接事件；不等同于完整网络流量审计。'}),
 base('process-audit','程序执行审计','进程与网络','记录 Agent 派生的程序执行','exec','*',['exec'],'notify','检测到程序执行，请确认其符合当前任务。','ActPlane · exec / notify',language,{note:'可能产生较多事件，按需选择。'}),
 base('instructions','安全约定文件','文件保护','保护 AGENTS.md 的写入和删除','filename','AGENTS.md',['write','unlink'],'block','安全约定由人工维护，请先提交修改说明并取得批准。','RQ1 · 契约文件约束提炼',corpus,{note:'这是可选约束；允许 Agent 维护约定文件的环境不应统一启用。'}),
 base('secret-egress','敏感信息外发','跨事件保护','读取敏感文件后限制网络连接','flow','.env',['connect'],'block','此进程已接触敏感文件。请使用已获准的脱敏或凭据处理流程。','ActPlane · 标签传播与信息流',language,{note:'标签会沿进程与文件传播，可能影响后续模型请求；应先核对来源范围。'}),
 base('remote-exec','网络输入后的执行','跨事件保护','观察接收网络输入后的程序启动','remote','sh\nbash\npython',['exec'],'notify','此进程接触过网络输入，请核对执行内容及来源。','RQ1 远程脚本约束 / ActPlane 信息流',corpus+'#L261',{note:'按网络来源标签匹配，不能精确等同于 shell 管道或脚本签名校验。'}),
];
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
export function runtimeRequirement(p){return ['suffix','filename','tail','flow'].includes(p.mode)?'当前受控引擎需启用文件后缀匹配；可保存配置，暂不能载入。':'';}
export function selectionReview(policies,selected){
 const chosen=policies.filter(p=>selected.has(p.id));
 return {chosen,invalid:chosen.filter(p=>!p.configured||validate(p)),pending:chosen.filter(p=>runtimeRequirement(p)),scope:'all-controlled-agents',inheritance:'system -> agent -> session/task'};
}
