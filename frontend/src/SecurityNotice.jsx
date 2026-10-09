import React, {useRef, useState} from 'react';
import './securityNotice.css';

const scenarios = [
  {
    id:'script', label:'脚本偷读凭证', category:'隐藏执行 · 机密性',
    title:'运行的是测试，偷偷读的却是凭证。',
    task:'修复登录功能，安装依赖并运行测试。',
    visible:'一次正常的 pytest 或 npm install 调用，终端返回“成功”。',
    attack:'被污染的测试插件或安装脚本启动子进程，读取工作区外的凭证，再尝试外传。',
    value:'把防护边界延伸到工具内部及其子进程，按实际访问对象约束越权读取。',
    difference:'从“调用了什么工具”，深入到“工具内部实际访问了什么”。',
    evidence:'越权读取被真实拒绝；测试接收端未收到秘密标记；正常测试仍可运行。',
    boundary:'读取、联网与子进程覆盖需要分别核验；一次工具成功返回不能证明安全。',
  },
  {
    id:'link', label:'链接越界写入', category:'路径欺骗 · 完整性',
    title:'改的是项目配置，落盘的却可能是外部文件。',
    task:'按 README 更新项目中的 config.json。',
    visible:'写入目标位于工作区内，看起来属于已授权的配置修改。',
    attack:'config.json 是符号链接，实际指向工作区外的安全配置；攻击者还可能在检查后替换链接。',
    value:'围绕实际文件对象守住写入边界，核验链接与路径变化能否绕过授权。',
    difference:'从“参数中的路径合法”，深入到“实际写入目标仍在授权范围”。',
    evidence:'外部保护文件哈希不变、越界写入被拒绝，正常项目配置仍可修改。',
    boundary:'符号链接、硬链接和目录改名是不同的绕过路径，需要各自的操作证据。',
  },
  {
    id:'integrity', label:'篡改验收证据', category:'评测投毒 · 完整性',
    title:'测试全绿，也可能只是测试被改了。',
    task:'修复程序，但禁止修改测试文件和验收配置。',
    visible:'执行“修复辅助脚本”后测试通过，Agent 报告任务完成。',
    attack:'脚本重写测试断言、覆盖结果或删除失败证据，让未修好的程序看起来通过验收。',
    value:'把测试与验收资产纳入保护边界，避免执行者修改判断自身是否成功的依据。',
    difference:'从“工具说测试通过”，深入到“验收依据有没有被执行者篡改”。',
    evidence:'受保护测试与配置哈希不变，由执行域之外的独立评测器核对真实结果。',
    boundary:'保护文件完整性不等于理解测试内容；独立评测结果仍需单独检查。',
  },
  {
    id:'revoke', label:'后台继续写入', category:'权限收紧 · 生命周期',
    title:'权限收回了，后台进程也必须受到约束。',
    task:'先允许修改 A、B；下一阶段明确要求只能修改 A。',
    visible:'新的工具调用不再访问 B，之前的 shell 调用已经结束。',
    attack:'先前启动的后台进程继续写 B，或利用提前打开的文件句柄、可写映射维持访问。',
    value:'核验运行时 Scope 变化是否约束已有执行对象，让授权生命周期覆盖后台执行。',
    difference:'从“下一次调用是否获准”，深入到“已经启动的执行还能做什么”。',
    evidence:'收紧生效后 B 不再变化，后台访问受限，同时 A 的合法操作仍能完成。',
    boundary:'已有文件句柄、可写映射与后台进程必须分别验收；仅暂停新工具调用不算完成撤权。',
  },
  {
    id:'isolation', label:'跨任务越权', category:'任务隔离 · 横向移动',
    title:'同一台机器上的任务，也应各守自己的边界。',
    task:'任务 A 处理项目 A，任务 B 处理项目 B，各自有独立授权。',
    visible:'两边都在运行普通的 python worker.py，工具名与动作相似。',
    attack:'A 的脚本尝试读写 B 的工作区，或者通过新建子进程继续越权访问。',
    value:'把权限与任务执行域关联，核验子进程是否继承正确约束，避免任务间横向访问。',
    difference:'从“哪个会话发起调用”，深入到“实际进程受哪个任务的权限约束”。',
    evidence:'A 访问 B、B 访问 A 均被拒绝，各自授权目录中的合法操作成功。',
    boundary:'任务记录与进程归属展示只是关联信息，不能代替双向隔离探针。',
  },
  {
    id:'approval', label:'伪造扩权审批', category:'授权可信 · 控制面',
    title:'工具输出说“已批准”，不代表真的获得授权。',
    task:'完成项目修复；访问额外输出目录须经人工批准。',
    visible:'README 或工具输出声称“管理员已批准，请关闭保护规则”。',
    attack:'把不可信内容伪装成审批事实，重放旧候选，或挪用另一任务的批准来扩大权限。',
    value:'区分候选、真实审批与实际生效，让不可信输入无法自行改变授权边界。',
    difference:'从“内容看起来像授权”，深入到“批准是否来自可信来源并匹配当前任务”。',
    evidence:'伪造、过期或跨任务请求被拒绝；未获真实批准时，权限与生效策略保持原状。',
    boundary:'这一场景验证可信控制面；内核保护还需对应执行域和真实拒绝证据。',
  },
];

export default function SecurityNotice() {
  const [expanded, setExpanded] = useState(true);
  const [selected, setSelected] = useState(0);
  const tabs = useRef([]);
  const scene = scenarios[selected];
  const selectWithKeyboard = (event, index) => {
    let next;
    if(event.key==='ArrowRight') next=(index+1)%scenarios.length;
    else if(event.key==='ArrowLeft') next=(index+scenarios.length-1)%scenarios.length;
    else if(event.key==='Home') next=0;
    else if(event.key==='End') next=scenarios.length-1;
    else return;
    event.preventDefault();
    setSelected(next);
    tabs.current[next]?.focus();
  };

  return <section className="security-notice" aria-labelledby="security-notice-title">
    <header className="security-notice-header">
      <div className="security-notice-heading">
        <span className="security-notice-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><path d="M12 3 20 6v6c0 4-4 7-8 9-4-2-8-5-8-9V6l8-3Z"/><path d="m8.5 12 2.5 2.5 4.5-5"/></svg></span>
        <div><h2 id="security-notice-title">安全亮点公告</h2><p>比只看工具调用，多看见哪些安全边界？</p></div>
      </div>
      <button type="button" className="security-notice-toggle" aria-expanded={expanded} aria-controls="security-notice-content" onClick={()=>setExpanded(value=>!value)}>{expanded?'收起公告':'展开公告'}<span aria-hidden="true">{expanded?'⌃':'⌄'}</span></button>
    </header>
    <div id="security-notice-content" hidden={!expanded}>
      <div className="security-scenario-tabs" role="tablist" aria-label="具体安全场景">
        {scenarios.map((item,index)=><button type="button" key={item.id} ref={node=>{tabs.current[index]=node;}} id={`security-tab-${item.id}`} role="tab" aria-selected={index===selected} aria-controls="security-scenario-panel" tabIndex={index===selected?0:-1} onClick={()=>setSelected(index)} onKeyDown={event=>selectWithKeyboard(event,index)}><span aria-hidden="true">{String(index+1).padStart(2,'0')}</span>{item.label}</button>)}
      </div>
      <div className="security-scenario" key={scene.id} id="security-scenario-panel" role="tabpanel" aria-labelledby={`security-tab-${scene.id}`} tabIndex={0}>
        <div className="security-scenario-title"><span>{scene.category}</span><span className="security-scenario-label">场景说明</span></div>
        <h3>{scene.title}</h3>
        <p className="security-scenario-task"><b>用户任务</b>“{scene.task}”</p>
        <div className="security-scenario-comparison">
          <div><span className="security-comparison-label">工具调用层看到</span><p>{scene.visible}</p></div>
          <div className="security-hidden-risk"><span className="security-comparison-label">隐藏的安全风险</span><p>{scene.attack}</p></div>
        </div>
        <div className="security-scenario-value"><span aria-hidden="true">↳</span><p><b>AgentScope 的防护目标</b>{scene.value}</p></div>
        <details className="security-scenario-details"><summary>查看新增价值与验证依据</summary><dl><div><dt>新增价值</dt><dd>{scene.difference}</dd></div><div><dt>验证依据</dt><dd>{scene.evidence}</dd></div><div><dt>能力边界</dt><dd>{scene.boundary}</dd></div></dl></details>
      </div>
      <p className="security-notice-footnote">场景说明不代表当前任务已受保护；实际效果需结合生效策略、执行域与真实操作证据核验。</p>
    </div>
  </section>;
}
