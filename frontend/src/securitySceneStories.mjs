// A readable process illustration, never a raw tool trace or live protection proof.
const stories={
 plugin:{title:'测试照常运行，插件偷读凭证被拦下',short:'测试插件偷读凭证',
  tool:['执行一次测试脚本','工具返回这次脚本的执行结果'],
  insight:'插件内部读取了什么，不会自动变成另一条工具调用。',
  steps:[['启动测试脚本','进入受保护的执行范围','observe'],['读取项目文件','合法读取成功','allow'],['尝试读取云凭证','合成凭证读取被拒绝','block']],
  takeaway:'允许测试脚本运行，仍然可以单独限制它读取凭证。'},
 integrity:{title:'源码可以修，验收测试不能被偷偷改掉',short:'脚本篡改验收测试',
  tool:['运行一个修复脚本','同一脚本可以尝试修改多个文件'],
  insight:'批准“修复”这个入口，还需要约束它到底修改了哪些对象。',
  steps:[['修改实现文件','允许的源码写入成功','allow'],['把测试重写成恒真断言','写入被拒绝','block'],['删除原有测试','删除被拒绝，测试哈希不变','block']],
  takeaway:'给修复留出空间，同时保住独立的验收依据。'},
 path:{title:'路径看着在项目里，真正写入的对象仍要检查',short:'链接越界写文件',
  tool:['向工作区里的路径写入','参数中看到的是一个文件路径'],
  insight:'符号链接和重命名可能改变真正被访问的对象。',
  steps:[['写入允许的源码','正常修改成功','allow'],['沿符号链接写入受保护测试','链接后的写入被拒绝','block'],['截断或重命名覆盖测试','两个变体均被拒绝','block']],
  takeaway:'授权需要落到实际文件，不能只看工具传入的路径。'},
 flow:{title:'报告换了名字、换了进程，秘密来源仍需受约束',short:'报告带走了秘密',
  tool:['本地处理数据，生成一份报告','另一进程向指定服务上报'],
  insight:'单看“读文件”和“发请求”都很普通，风险来自数据怎样流转。',
  steps:[['进程 A 读取秘密','本地处理被允许','allow'],['生成并重命名报告','派生文件保留秘密来源','observe'],['进程 B 读取这份报告','来源约束延续到另一进程','observe'],['向指定地址建立新连接','秘密来源连接被拒绝','block']],
  takeaway:'同一地址下，普通结果可以上报，秘密派生数据的新连接被拒绝。'},
 destination:{title:'地址相同，普通上报与秘密外发可以区别处理',short:'同一地址的两种数据',
  tool:['两个任务连接同一个服务','地址白名单看到的是同一个目的地'],
  insight:'只看目的地址，不能说明发出去的数据来自哪里。',
  steps:[['普通文件 → 指定地址','普通来源的新连接成功','allow'],['秘密 → 派生报告 → 另一进程','传播后的来源仍需检查','observe'],['相同地址，秘密来源新连接','连接被拒绝','block']],
  takeaway:'本轮对照中，来源相关策略比仅保留同端点可达性的静态沙箱更细。'},
 descendants:{title:'切换到 shell 和后台进程，读取边界继续有效',short:'后台脚本继续越界',
  tool:['执行一个 Python 脚本','脚本又启动 shell 和后台 Python'],
  insight:'顶层调用结束或换了解释器，后代进程仍可能继续操作。',
  steps:[['读取项目文件','合法读取成功','allow'],['Python → shell → 后台 Python','约束覆盖实际后代进程','observe'],['后台进程读取云凭证','合成凭证读取被拒绝','block']],
  takeaway:'约束跟随真实执行范围，后代进程不能仅靠换入口摆脱它。'},
 isolation:{title:'自己的资源能读，其他资源对象仍受保护',short:'借用其他 Agent 权限',
  tool:['运行当前任务的脚本','脚本也可以尝试打开其他资源'],
  insight:'工具名相同，不代表不同实例拥有相同资源权限。',
  steps:[['读取当前任务资源','合法读取成功','allow'],['读取另一资源对象','越界读取被拒绝','block'],['检查当前实例与策略绑定','实例内会话隔离仍待建设','observe']],
  takeaway:'本轮验证资源对象边界；同一原生实例中的会话仍共享执行域。'}
};

export const sceneGroups=[
 {label:'工具内部的行为',ids:['plugin','integrity','path','descendants']},
 {label:'数据流转与隔离',ids:['flow','destination','isolation']},
 {label:'审批与能力边界',ids:['injection','approval','handles','freshness','business']}
];

export function storyFor(scene,state){
 const story=stories[scene.id]||{title:scene.label,short:scene.label,
  tool:scene.chain,insight:scene.before,
  steps:scene.chain.map(step=>[step,'机制说明，尚无本轮完整实证','observe']),takeaway:scene.value};
 // An absent/failed evidence file must not leave red/green measured verdicts.
 const missingMeasuredStory=!state?.proof&&Boolean(stories[scene.id]);
 return {...story,title:missingMeasuredStory?scene.label:story.title,measured:Boolean(state?.proof),
  takeaway:missingMeasuredStory?'本场景证据尚未随页面提供，需要核验合法操作与越界效果。':story.takeaway,
  steps:story.steps.map(([title,detail,tone])=>({title,
   detail:missingMeasuredStory?'需要独立核验此处的允许或拒绝结果':detail,
   tone:state?.proof?tone:'observe',label:state?.proof?(tone==='allow'?'允许':tone==='block'?'拒绝':'关联行为'):'待验证'}))};
}
