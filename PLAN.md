# 当前交付

更新：2026-11-18。用户已授权 PR #44 及本轮后续 PR 连续合并，无需逐项确认。第四步六项均已合并 main，最新为 `be311ca`；E/F08 已同步该基线，准备合并。

## 已合并能力

前序 PR #38–#42 已完成 D2、D3、旧接口计量与预算、用量 CSV 和 D2 三项后续修复。

| 第四步项目 | PR | merge SHA |
| --- | --- | --- |
| A1-2 保存规划后准备 | [#43](https://github.com/King70404/AI-Writer-project/pull/43) | `530a8ce` |
| A1-1 检查连接 | [#44](https://github.com/King70404/AI-Writer-project/pull/44) | `eca5975` |
| A2-1 全书架汇总 | [#47](https://github.com/King70404/AI-Writer-project/pull/47) | `8543a06` |
| A2-2 到期伏笔与预算提醒 | [#48](https://github.com/King70404/AI-Writer-project/pull/48) | `9c56462` |
| B-2 分析/评审发送前预估 | [#45](https://github.com/King70404/AI-Writer-project/pull/45) | `f15bdb8` |
| B-3 缓存计价、迁移及费用 CSV | [#46](https://github.com/King70404/AI-Writer-project/pull/46) | `be311ca` |

各项独立完整 Windows 门禁与最新 main 同步补验证据见对应 `docs/*WINDOWS_GATE*.md` 和 PR。普通 merge、未绕过保护；GitHub hosted Windows 检查受账户付款/额度问题阻止，任务未执行，不声称云端测试通过。

## 当前最终候选

E/F08 [PR #49](https://github.com/King70404/AI-Writer-project/pull/49)：规则场景元数据、作者手工标注、冻结来源 A/B 试写、评分后揭示方法、作者验证后模板跨书复制。两臂串行，复用台账与预算，不自动重发或采用。

代码 `8dcf46cfa9b91806acb5225268e37ccdb3301a15` 完整 Windows IncludeE2E 通过：后端 3,334，前端 1,098，E2E 34 场景及清理；覆盖率、日志散列和修复记录见 [F08 验证](docs/F08_WINDOWS_GATE_20261117.md)，操作与边界见 [方法验证](docs/METHOD_VALIDATION.md)。同步 main 后已逐文件核对：除 PLAN 和 docs 外整个仓库与该已验证候选无差异，复用有效完整门禁证据，不冒充新 head 重跑过完整门禁。

## 下一步

完成 F08 同步核对并按已有授权合并，随后同步最终状态。未发布、未打 tag；不再要求本轮逐项合并确认。

## 边界

只用假传输与自有隔离数据；不接触正式创作数据或真实 Key，不调用真实/付费模型；不发布、不打 tag、不 force push。运行时正文、事实和规则仍由作者确认后采用，不改冻结验收文件。工程测试不等同真实模型文学效果评价。
