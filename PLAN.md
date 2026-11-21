# 当前交付

更新：2026-11-21（C/D 系列已合并，见下节）；此前 2026-11-18：用户已授权 PR #44 及本轮后续 PR 连续合并，无需逐项确认。第四步六项和第五步 E/F08 均已合并 main。功能合并基线为 `16adc1e39e66a69dfb1b20174c3c1dd51cb04978`；后续提交仅同步状态文档。

## C/D 系列（2026-11-21 合并）

经作者授权按 #52→#60 顺序合入 main：

| 项目 | PR | merge SHA |
| --- | --- | --- |
| C-3 评审使用召回策略 | [#52](https://github.com/King70404/AI-Writer-project/pull/52) | `0459d69` |
| D3-S 场景进度（0021） | [#53](https://github.com/King70404/AI-Writer-project/pull/53) | `a606531` |
| C-1 AI 建议拆分规划（0022） | [#54](https://github.com/King70404/AI-Writer-project/pull/54) | `c863468` |
| C-2 批量提取伏笔建议（0023） | [#55](https://github.com/King70404/AI-Writer-project/pull/55) | `157f636` |
| D3-C 整章候选稿（0024） | [#56](https://github.com/King70404/AI-Writer-project/pull/56) | `c3c54d5` |
| #57 建议卡修改/撤销、#58 窄栏与分段编辑、#60 C-4 语义索引（0025）、#59 F03 事件/人物状态（0026）及集成修复、E2E-INT-031 | [#61](https://github.com/King70404/AI-Writer-project/pull/61) | `5c8ced4` |

#57–#60 的提交全部随 #61 进入 main，已注明后关闭。合并后的 main 与 Windows 门禁全绿的候选 `7cc6dc9`（另加纯文档提交）零差异：PR run `44904813807` Default/Full、push run `44904808094` Default 通过，后端 3,443、前端 1,175、E2E 35 场景。需在 Windows 本地再验证的项目（旧数据升级到 0026、启动器实机、字体缩放下窄栏、真实嵌入/生成模型费用与效果、撤销中断边界、F03/D3-S 浏览器流程）见 [C/D 集成门禁](docs/C_D_INTEGRATION_WINDOWS_GATE_20261121.md)。

## 已合并能力（2026-11-18）

前序 PR #38–#42 已完成 D2、D3、旧接口计量与预算、用量 CSV 和 D2 三项后续修复。

| 第四步项目 | PR | merge SHA |
| --- | --- | --- |
| A1-2 保存规划后准备 | [#43](https://github.com/King70404/AI-Writer-project/pull/43) | `530a8ce` |
| A1-1 检查连接 | [#44](https://github.com/King70404/AI-Writer-project/pull/44) | `eca5975` |
| A2-1 全书架汇总 | [#47](https://github.com/King70404/AI-Writer-project/pull/47) | `8543a06` |
| A2-2 到期伏笔与预算提醒 | [#48](https://github.com/King70404/AI-Writer-project/pull/48) | `9c56462` |
| B-2 分析/评审发送前预估 | [#45](https://github.com/King70404/AI-Writer-project/pull/45) | `f15bdb8` |
| B-3 缓存计价、迁移及费用 CSV | [#46](https://github.com/King70404/AI-Writer-project/pull/46) | `be311ca` |
| E/F08 方法验证 | [#49](https://github.com/King70404/AI-Writer-project/pull/49) | `16adc1e` |

各项独立完整 Windows 门禁与最新 main 同步补验证据见对应 `docs/*WINDOWS_GATE*.md` 和 PR。普通 merge、未绕过保护；此前 GitHub hosted 检查曾因账户付款/额度未启动，后续实际恢复执行并通过，最新云端证据见下节。

## 最终有效验证

E/F08 [PR #49](https://github.com/King70404/AI-Writer-project/pull/49)：规则场景元数据、作者手工标注、冻结来源 A/B 试写、评分后揭示方法、作者验证后模板跨书复制。两臂串行，复用台账与预算，不自动重发或采用。

代码 `8dcf46cfa9b91806acb5225268e37ccdb3301a15` 完整 Windows IncludeE2E 通过：后端 3,334，前端 1,098，E2E 34 场景及清理；覆盖率、日志散列和修复记录见 [F08 验证](docs/F08_WINDOWS_GATE_20261117.md)，操作与边界见 [方法验证](docs/METHOD_VALIDATION.md)。同步 main 后已逐文件核对：除 PLAN 和 docs 外整个仓库与该已验证候选无差异，复用有效完整门禁证据，不冒充新 head 重跑过完整门禁。

## 最新云端 CI 证据

2026-11-18 已成功恢复云端执行。初次 Full run `44314297025` 后端 3,334 项通过，前端一项测试未等待最近章节存储 effect 完成而失败；原证据保留。

测试修复候选 `78761f6dfe07a2e203dfcbb130bd703bfc7b1b3b` 的 [GitHub run 44318315626](https://github.com/King70404/AI-Writer-project/actions/runs/44318315626) Windows Default/Full 均通过：后端 3,334、前端 1,098、E2E 34 场景和清理。artifact status=passed、blocker=null。已通过 PR #50 合并为 `1cc426d`，后续仅同步状态文档。详细结果、覆盖率、日志散列和失败/修复过程见 [CI 重试记录](docs/CI_RETRY_20261118.md)。不将文档更新 SHA 冒称为另一次 Full 通过。

## 下一步

C/D 系列已合并；剩余为上述 Windows 本地验证、真实模型费用与文学效果评估（作者）。此前：本轮任务已完成，无待合并的 A/B/E PR。合并顺序、补验与主线一致性见 [收尾记录](docs/AB_E_MERGE_COMPLETION_20261118.md)。不将工程测试视为真实付费模型或作者文学效果验收；未发布、未打 tag。

## 边界

只用假传输与自有隔离数据；不接触正式创作数据或真实 Key，不调用真实/付费模型；不发布、不打 tag、不 force push。运行时正文、事实和规则仍由作者确认后采用，不改冻结验收文件。工程测试不等同真实模型文学效果评价。
