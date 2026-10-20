# 全模块宽度修复验收

## 范围

main 基线 151d39d。仅修改 `frontend/src/recordVisuals.css` 与 `frontend/src/unifiedPolicyLibrary.css` 的生产布局；配套设计合同、RFC/ADR/BUG 和 CSS 单独发布脚本。已有 Pi 工作区读取器相关后端及文档改动保留，不纳入本次提交或发布。

## 已完成验收

前端 403/403 与构建通过；浏览器预览保持 18003 当前 JS `main-CRIh8RoI.js`，仅换 CSS。

| 尺寸/情形 | 结果 |
|---|---|
| 1920px 七个模块 | 主内容等于 main；无页面横向溢出 |
| 1280px 七个模块 | 主内容 1064px，与 main 相等 |
| 600px 七个模块 | 主内容 542px，与 main 相等；宽表内滚动 |
| 系统主表 1920px，侧栏展开 | 表 1635px，等于容器 clientWidth，不再为 836px |
| 系统主表 1920px，侧栏收起 | 表 1783px，等于容器 clientWidth |
| Agent 指定目标后助手外框 | 1652px，max-width none；未发送生成请求 |
| 子配置 600px | 主表内容 836px，子表内容 660px，子表可视 471px；详情留在主表可视区 |
| 列宽与系统子页 | 键盘微调 300→310，刷新恢复 300；标签管理/生成记录宽度正常 |
| 浏览器日志 | 无 console error/warn |

截图与 `width-measurements.json` 位于指定文档目录 `REVIEW/evidence/full-width-20261020/`。首次总览公告曾阻挡导航，关闭后重新逐页等待准确 data-page 再测量；不把被弹窗阻挡的点击当成功。

## 发布边界

发布脚本逐字节验证新 CSS 相对线上旧 CSS 只包含主内容全宽、助手外框全宽、移除通用 1440px 上限和模板表 min-width 的指定变换。保留所有生产 JS、终端和其他资源，更新前核对 index 固定哈希；不重启服务或 Agent，不应用策略，不推送远端。

## 18003 发布与复验

- main 功能提交 `a67dbd6`；2026-10-20 19:10:16 仅发布 CSS。JS 仍为 `main-CRIh8RoI.js`，CSS 为 `main-CXG-2KhO.css`，SHA-256 `0ecf7cd7fa62cca1310968070dbf01c4e925ceec2bdb399f0a8b93a03508aa4d`。
- index SHA-256 `0b66a0a8e46a9d510063a146e62dfc1f3e91307d2f69dc7d0fc2764c5d7daa26`；备份及发布回执 `/var/lib/agentscope-scope-demo/release-backups/layout-width-20261020-191016/`。
- 发布前后 API/Broker 进程身份、Agent/策略权威状态、引擎和已有 JavaScript 均通过不变检查。工作期间另一项 Pi 读取器任务已有独立本地提交及 API 发布，不归为本次 CSS 行为，不声称整段任务期间服务均未变化。
- 18003 全部七个模块逐页复验：1920px 视口下 content 与 main 均为 1704px，未出现页面横向溢出；线上策略记录加载完成后截图为 `published-system-1920.png`，测量为 `published-measurements.json`。
- 未重启服务或 Agent、未生成/审批/应用策略、未推送远端。
