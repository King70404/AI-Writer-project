# 验收稳定性与 Green Candidate

本文件只定义候选进入正式验收的条件。开发范围与阶段顺序见根目录 `AGENTS.md`、`PLAN.md` 和当前任务；已授权的大交付阶段可以连续完成相邻开发步骤，正式验收仍须独立记录。

## 执行模式与失败处理

- **Development / CI**：失败是开发反馈；在已授权范围内诊断、修复并重跑适用检查，直到阶段完成定义满足。
- **RC preflight**：验证已冻结的精确候选。规定检查失败时保留首个失败证据并停止本轮；修复进入独立的 Development recovery 记录，形成新候选后重新验证，不修改冻结候选后悄悄续算通过次数。
- **Formal acceptance**：只能验证已完成全部 RC preflight 的精确 SHA，并独立记录候选、检查与结果。正式门失败立即保留证据并停止该轮；不得在同一验收任务中修改候选或擅自重跑失败正式门。修改与再次验收须有新的、明确的恢复任务授权。

不得用 timeout inflation、sleep、retry、skip、删除测试、降低 coverage、静音 warning 或弱化断言制造绿色。普通单测和开发检查不会因失败自动变成正式验收。

## Green Candidate 最低条件

创建 formal acceptance Issue 前，同一冻结 candidate 必须全部满足：

1. Default `scripts/quality_gate.ps1` PASS。
2. `scripts/quality_gate.ps1 -IncludeE2E` 在 Development / RC preflight 模式下连续 PASS 两次。
3. Windows 根目录 `启动 AI 网文助手.cmd` launcher smoke PASS 一次。
4. 当前任务要求的隔离真实作者 smoke PASS 一次。
5. Git worktree / staging clean；candidate SHA、PR head 与 base 均已锁定。
6. 无 migration / schema / tag / frozen-history 非授权漂移。
7. 不读取、枚举或修改正式 `%LOCALAPPDATA%\AIWebNovel` 作者数据；测试只使用并清理各自拥有的隔离根。
8. 前端与浏览器测试没有未解释的 React warning、`console.error`、pageerror 或 requestfailed；预期 warning/error 必须按测试契约明确 allowlist 与原因。
9. 已知 timing-sensitive 测试完成下述专门稳定性验证。

launcher smoke 必须实际走上述 `.cmd`。启动进程需把 `LOCALAPPDATA` 临时指向任务自有的仓库外目录，使其默认 `AIWebNovel` 数据根落入隔离位置；不得使用作者真实数据根完成烟测。

任何新 commit 都会清零连续绿色计数。已有 Development PASS、单次 IncludeE2E PASS 或旧候选结果不能替代本候选的完整证据；Default 没有运行浏览器。

## 开发期稳定性检查

- timing/flaky failure 先排查过大的单测、重复逐字符输入、不必要的异步等待、非法受控输入状态、资源争用、环境污染及共享状态。不要先把 5 秒 timeout 改为 10 秒。
- 可独立验证的行为拆成单测；保留需要 `user-event` 的真实交互语义，不全局换成 `fireEvent`。完整流程由少量 E2E 覆盖。
- 修复曾失败的 timing-sensitive 测试后，精确测试独立运行 **20 次**，所属文件独立运行 **5 次**，均须 0 failure、0 unexpected warning。任一次失败即表明仍不稳定，修复后重新计数。
- React warning / `console.error` 必须解释或修复，例如数字框清空时向受控 `value` 写入 `NaN`。逐步让前端测试环境直接拒绝未 allowlist 的 warning/error，不靠静音通过。

## 作者界面与删除回归

- 优先使用 `getByRole` / `getByLabel`，配合 `exact: true`、region/form scope 或 chaining/filtering；只有明确测试契约需要时才用 test id。不得依赖宽泛 substring 定位同页的 `书名` / `确认书名` 等名称。
- 修改作者文案时，逐项核对创建、编辑、保存反馈和冲突处理的真实可访问名称；不同模块的按钮不能靠全局替换同步。场景必须运行到最终请求、持久化和浏览器安全审计，越过首个失败点不代表 PASS。
- 涉及作者界面的 PR，Development 交接前先跑受影响的独立 E2E，再跑完整 `npm run e2e`，保留真实结果；这不替代 RC 两次 IncludeE2E 与正式验收。
- 删除小说必须验证捕获的子内容旧历史链接，以及历史列表、旧 cursor 页、旧/当前修订正文 API 均拒绝普通读取；父页面 404 或小说从列表消失不足以证明通过。
- 逻辑删除保留原修订并允许追加删除标记。真实迁移数据库回归逐条比较删除前已存在的修订内容，不要求删除前后整张修订表完全相同。
- 普通作者页面必须隐藏内部 ID / 并发信息，保留有用的历史版本、保存时间和冲突处理信息。

## CI 与合并准备

[QA-HARDEN-2 #17](https://github.com/King70404/AI-Writer-project/issues/17) 必须在 RF-01 前完成：

- Windows GitHub Actions 或等价 GitHub-visible CI；PR 每次更新跑唯一名称的 Default check，merge-ready / RC 跑 IncludeE2E。
- 失败保留日志/产物；CI 仅使用 ephemeral / isolated data，不以复制本地日志冒充服务器上的最新 SHA check。
- 提供可重复执行已知 timing-sensitive 测试或候选 preflight 的稳定性入口，首次失败即停止，不用 retry 隐藏失败。
- main 的 required status checks 绑定最新 SHA，并要求分支 up to date。须由 owner 配置或受账户套餐限制时，记录精确待办与限制，不宣称已经启用，也不降低检查要求。

## 冻结与交接顺序

1. 完成开发修复、适用测试与稳定性检查，同步 `PLAN.md` 和活动 Issue / PR。
2. 明确 main、PR head、base 与 candidate 状态，**在 RC preflight 前冻结 SHA**。
3. 对同一冻结 SHA 执行：`Default → IncludeE2E #1 → IncludeE2E #2 → launcher smoke → isolated author smoke → Git / migration / tag / frozen-history / cleanup 复核`。
4. 冻结期间动态结果写入活动 Issue / PR，不仅为协调状态向 main 追加 commit；candidate 最终 PASS/FAIL 后再同步 `PLAN.md`。
5. 全部 PASS 后创建绑定该 SHA 的独立 formal acceptance；正式验收 PASS 且满足当前任务的合并授权后才 merge。

晚期失败必须把可前移的检查补到 Development / CI / RC preflight。历史证据按需查阅：[Q1 #10](https://github.com/King70404/AI-Writer-project/issues/10)、[Q2 #14](https://github.com/King70404/AI-Writer-project/issues/14)、[RC1 #18](https://github.com/King70404/AI-Writer-project/issues/18)、[R3 #19](https://github.com/King70404/AI-Writer-project/issues/19)、[R4 #20](https://github.com/King70404/AI-Writer-project/issues/20)；这些已完成或失败的轮次不作为当前任务顺序。
