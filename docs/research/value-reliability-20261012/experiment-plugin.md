# 测试入口内的凭证读取

验证日期：2026-10-12。环境：6.6.114.1-microsoft-standard-WSL2。ActPlane 二进制 SHA-256：`5e8d43c279d88bd4215f654746675debfd976e28426c9fabdabeca408865d6da`。

合成凭证读取被拒绝，合法源码读取成功。

静态隐藏凭证目录也能阻止；本轮是插件行为载荷，未复现某个真实插件漏洞。

## 方法与对照

这是已选攻击载荷的执行效果实验；每组重复三次。未评估提示注入成功率，未部署 CaMeL、Progent、FIDES。入口对照只批准外层命令，不检查载荷内部的后续系统调用；不能泛化为所有工具层权限系统。静态沙箱使用 bubblewrap，只读根、允许的源码及输出目录可写、凭证目录隐藏或另一资源被遮蔽；网络对照保留相同端点可达性。

| 执行方式 | 合法任务完成 | 不安全效果发生 | 内核拒绝证据 |
|---|---:|---:|---:|
| 执行层无约束对照 | 3/3 | 3/3 | 0/3 |
| 仅检查工具入口的对照 | 3/3 | 3/3 | 0/3 |
| 等价任务能力的静态沙箱 | 3/3 | 0/3 | 0/3 |
| ActPlane | 3/3 | 0/3 | 3/3 |

## 可复现证据

完整原始记录见 `../../REVIEW/evidence/value-reliability-20261012/scenarios-final.json`，含每次载荷、执行命令、策略、实际操作结果、文件前后哈希、接收端内容和真实内核事件。全部使用合成数据和回环接收端。界面只显示摘要，不向客户展示原始 JSON。

示例已加载策略：

```yaml
version: 1
policy: |
  source AGENT = exec "**/python3"
  rule boundary:
    block read file "/tmp/av-xth2xfdf/plugin-actplane-0/credentials/cloud.key" if AGENT
    because "Synthetic approved task boundary."
```

## 失败记录及限制

首轮未设置 ACTPLANE_RESERVE_OPEN_RULES，三个读取类场景的 ActPlane 规则载入失败，共九条失败记录，保留于 scenarios-initial-failure.json。修正实验启动配置后重新执行全部 72 条。规则载入失败不能记为保护成功。

本报告的“完成”是确定性载荷中的合法操作完成，不等于真实 Agent 业务任务完成、安全反馈送达或模型正确修复。原生 DSH 补充任务另记。预先打开的连接、共享内存、撤权前 mmap、远程业务语义不由本结果证明。
