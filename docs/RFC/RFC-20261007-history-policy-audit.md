# 历史任务中的策略与审计

状态：已实现，接口与回归通过，浏览器最终验收进行中。

保留Agent连接、策略工作台、任务历史三个一级模块。一任务一份档案，内部明确为任务概况、运行前策略、运行时策略、执行审计、结束结果。策略工作台的当前任务选择只显示可继续操作的任务，旁边提供历史策略与审计入口，结束任务不会伪装为当前在线实例。

档案策略列表与详情直接读取现有启动生成作业、候选、运行时作业、审核、版本及加载回执，保留同任务所有生成结果。加载回执注明历史，不代表目前active；详情包含逐条规则、DSL、证据和关联审核/版本。既有阶段原始记录继续在内部提供，不删除旧数据。

执行审计分OS拦截与核验、DSH工具调用、控制面记录。OS行显示操作、对象、实际结果、PID、domain、命中规则和动作来源；独立验收探针不能标作DSH工具行为，工具成功不能作为内核允许证明。历史查询不调用Pi、DSH或Broker探测，不恢复任务，不更改权限。

新增GET /api/tasks/{task_id}/archive/policies?stage=startup|runtime、/policies/{record_id}以及/audit?category=os|tools|control。关联只在task_id内；分页按真实记录游标。history_only/historical=true、live=false。archivePane在URL中保存内部页签，历史查询不改变工作台当前任务。
