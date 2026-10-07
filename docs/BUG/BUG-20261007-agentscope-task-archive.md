# BUG：任务档案与审核问题闭环

日期：2026-10-07。状态：列出问题均已修复并完成对应回归、真实任务或界面核对。

## 审核代次竞争

旧审核成功尾部曾清掉新候选，失败尾部曾恢复后来暂停的门。修复：成功仅追加原job解决收据；失败恢复须原revision/version/hash/binding/applying一致。旧运行核验要求精确runner PID及预期cgroup，不能只看同域号。竞争回归覆盖新候选、新暂停、不同PID和未核验cgroup。

恢复曾丢未审收紧意图、历史loading曾借当前session。修复：保留pending_restriction_intent并登记candidate_invalidated；旧版本读取原job上下文和历史收据，不回填当前会话。相应恢复与历史身份回归通过。

审核入口验hash后旧执行仍可能改来源。修复：install(review_sources=...)在quiesce后、launch前重验；stop中修改真实临时文件的测试证明不launch、phase/gate failed、旧新凭据撤销。

## 档案事实与默认可见性

创建事件曾继承tasks后来failed，修为created；header保留当前/最终状态。同一内核事件managed/runtime镜像曾双计，现仅按同任务同hash排重。

operation_verified曾丢probe/分类/影响/哈希/kernel元数据，kernel丢probe标志。修为结构化安全白名单，并将action_source与存储表分离；新增6回归和部署后真实事件19458验证。

超过300条执行事件时，前端只从近期页挑摘要，更早v3/v4加载被埋分页。修为每阶段全任务关键highlights最多20，真实加载/结束优先，排除高频pause/probe及nochange/guidance候选；主分页不变。新增125轮后续活动及45审核竞争测试，archive65 passed。最终字段记录页真实显示v3/v4加载和人工审核，桌面/423px核对通过。

## 当前连接历史混入

inventory曾返回stopped managed，offline还因旧PID available=true。修为DB fallback仅web+running/recovering/generating；failed仅本轮独立connected证据可处理DB竞争，失联即移除。native offline登记保留。连接targeted55通过，真实423px连接表已验收。

## 探针权限与验收纠正

umask077令root探针登记文件变0600，API无法读；可信目录fd、文件类型/所有权/单链接校验后显式fchmod0640。root真实权限8项通过，任务恢复及结束完成。详见[独立问题记录](BUG-20261007-探针登记权限受umask影响.md)。

v3 rotation的old_credential_http误用了admin路由，不计为plugin旧凭据重放；轮换撤销靠权威DB revoked。结束阶段才有真实原plugin gate关闭前200/关闭后401，公开证据不复制凭据值或哈希。

最终首次全量400passed/52skipped/1failed由tempfile默认/var/tmp随机目录超DSL64字节触发，安全compiler未改；本轮最终短TMPDIR=/tmp/a和basetemp=/tmp/a/t复验403passed/52skipped。该诊断保留，不算模型失败或生产逻辑修复。

## 档案缺少离线域图/DSL与部分材料提示

既有managed topology.graph依赖workbench/Broker，不能满足离线档案。新增archive历史图/域详情，版本和PID只取同任务policy_active，材料读取复用root-owned/hash核验助手。禁止借当前PID、合成D0或父子关系。缺失材料返回unavailable，跨任务/版本拒绝。

独立安全评审又复现task材料可信、baseline对象存在但缺expected hash时notice被错误置空。修为依据missing_sources而非baseline对象存在判断，组合回归断言task可用但notice仍明确提示基线缺hash。历史图7项新增回归及最终后端410项通过，最终历史图实屏已核验v3/v4版本和DSL，缺失底线材料明确报告。

## 连接TTL矛盾

缓存达到TTL8秒时曾只清connected、仍留available=true。connections整改为同时清connected/available，并核对7.999秒/8秒边界与require拒绝过期观察。该专项根任务报告3passed/38deselected；不是重新探测或由历史状态推定离线。

## 直接URL恢复后的焦点

档案刷新后以body作为原始焦点，Escape关闭未回到任务行。给档案入口稳定任务ID，关闭后优先恢复有效原焦点，否则定位当前任务入口，再回退搜索框；在React提交后的动画帧执行。实际URL后退、刷新、Escape关闭后AX焦点为archive-open-bef449047cd24af6，列表搜索与已结束筛选保持。
