# Acceptance Stability / Green Candidate Protocol

本文件定义 AIWebNovel 在进入 formal acceptance 之前必须满足的稳定性条件。目标不是声称“软件永远不可能失败”，而是把可发现的代码、测试、环境和 UX 问题尽量前移到 Development / CI / RC preflight，避免 formal acceptance 成为第一次完整运行。

## 1. 为什么新增本协议

项目历史中已经出现多次“开发检查绿，但正式验收才第一次发现新 blocker”的情况：

- V1-OPS locator 歧义：作者入口文案变化后，Playwright 宽泛 accessible-name locator 同时匹配多个元素。
- V1-UX Q1：`书名` 同时匹配 `书名` 与 `确认书名`，formal IncludeE2E 首次暴露 strict-mode violation。
- V1-UX Q2：在修复 locator 后直接再次进入 formal acceptance，结果 frontend coverage 阶段才首次暴露 `novel-structure-workspace.test.tsx` 5000ms 边界超时；同一运行还出现 `Received NaN for the value attribute`。
- TXT export smoke 曾出现浏览器观察环境差异，需要独立 Playwright/Chromium 交叉验证才能确认产品本身无缺陷。

共同模式：**正式验收太早，完整候选稳定性没有在 Development 阶段被重复证明。**

## 2. 核心原则

### Formal acceptance 不是发现问题的首轮测试

formal acceptance 只能验证一个已经完成 RC preflight 的精确 SHA。若候选从未完整跑过与正式门等价的测试链，则不得创建 formal acceptance Issue。

### 失败要前移，不要隐藏

允许 Development / CI / RC preflight 失败，并要求在这些阶段发现问题。禁止通过增加 timeout、sleep、retry、skip、降低 coverage、删测试或弱化断言来制造绿色。

### 精确 SHA

所有稳定性证据都绑定精确 candidate SHA。候选有任何新 commit，连续绿色计数清零，必须从新的 SHA 重新开始。

## 3. Green Candidate 进入 formal acceptance 的最低条件

候选必须同时满足：

1. Default `scripts/quality_gate.ps1` PASS。
2. `scripts/quality_gate.ps1 -IncludeE2E` 在 **Development / RC-preflight 模式**下对同一 SHA 连续 PASS 两次。
3. Windows `启动 AI 网文助手.cmd` launcher smoke PASS 一次。
4. 当前任务要求的隔离真实作者 smoke PASS 一次。
5. Git worktree/staging clean；candidate SHA、PR head、base 均已锁定。
6. 无 migration/schema/tag/frozen-history 非授权漂移。
7. 不读取或修改正式 `%LOCALAPPDATA%\AIWebNovel` 作者数据。
8. 前端/浏览器测试无未解释的 `console.error`、React warning、pageerror 或 requestfailed。确有预期 warning/error 时必须在测试契约中明确 allowlist 与原因。
9. 已知 timing-sensitive 测试已完成专门的重复稳定性验证。

只有上述全部满足，才创建 formal acceptance Issue。

## 4. Timing / flaky 测试处理

### 不先加 timeout

Vitest Node/jsdom 默认 test timeout 为 5000ms。测试接近或越过该边界时，先判断是否属于：

- 单个测试包含过多独立业务行为；
- 重复使用 `user-event` 模拟大量逐字符输入；
- 不必要的异步等待；
- 受控输入出现非法中间状态；
- 资源争用或环境污染；
- 测试之间存在共享状态。

不得把“把 timeout 从 5 秒改成 10 秒”作为第一修复手段。

### 拆分 mega-test

一个 jsdom 单测如果同时测试多个可独立验证的行为，应拆成更小的测试，使失败信号更精确、运行更快、重现更稳定。

保留真正需要 `user-event` 的用户交互语义；不要为了速度全局替换为 `fireEvent`。但不要用一个单测重复模拟整个端到端写作流程——这类完整流程应由少量 E2E 覆盖。

### 重复稳定性验证

曾发生 timing/flaky failure 的测试在修复后至少：

- 精确失败测试独立运行 20 次，0 failure，0 unexpected warning；
- 所属测试文件独立运行 5 次，0 failure，0 unexpected warning。

任何一次失败都表明仍不稳定；修复后重新计数。

## 5. React / console warning policy

开发测试中出现未解释 warning 不能当成“只是日志”。例如 number input 在 clear 时把 `valueAsNumber` 的 `NaN` 写入受控 `value`，会产生 React warning；这类非法中间状态必须修复，而不是静音 console。

逐步把 frontend 测试环境改造成：未 allowlist 的 React warning / console.error 直接导致测试失败。

## 6. Playwright locator policy

优先：

1. user-facing `getByRole` / `getByLabel`；
2. `exact: true` 或稳定的 region/form scope；
3. chaining/filtering；
4. 只有明确测试契约需要时才使用 test id。

新增或修改作者文案时，必须检查同页是否出现同前缀 accessible name，例如 `书名` / `确认书名`。不得依赖宽泛 substring locator。

## 7. CI / GitHub merge readiness

在 RF-01 之前完成 QA-HARDEN-2：

- Windows GitHub Actions（或等价 GitHub-visible CI）；
- PR 每次更新跑 Default gate；
- merge-ready / RC 跑 IncludeE2E；
- 失败保留日志/产物；
- CI 仅使用 ephemeral / isolated data；
- main 的 required status checks 绑定最新 SHA；
- main 需要 up-to-date branch 才能 merge。

若 GitHub 管理权限需要仓库 owner 手工设置，必须明确记录 owner action，不能假装已经开启。

## 8. RC freeze / 协调文档规则

开始最终 RC preflight 前：

1. 先同步 `PLAN.md`、活动 Issue / PR；
2. 将 main 与 candidate 同步到明确状态；
3. 冻结 candidate SHA；
4. preflight 期间不要仅为了状态说明而向 `main` 追加协调 commit；动态状态写到活动 Issue/PR；
5. candidate 最终 PASS/FAIL 后再同步 `PLAN.md`。

这样避免因为纯文档 commit 让已经验证的 candidate 无故落后于 base。

## 9. 分阶段 Pipeline

建议固定为：

`开发期窄测试 → Default gate → timing/flaky stress → RC IncludeE2E #1 → RC IncludeE2E #2 → launcher smoke → isolated author smoke → SHA freeze → formal acceptance → merge`

正式验收阶段如果仍失败，必须保留 hard-stop；但每一次晚期失败都要把对应检查前移到更早门禁，避免同类问题再次只在 formal 阶段出现。

## 10. 当前 V1-UX 恢复顺序

1. #14 已作为失败 formal acceptance 关闭保存。
2. #16 `V1-UX-1-R2`：修复 novel-structure NaN / timeout instability，并执行重复稳定性验证。
3. #15 `QA-HARDEN-1`：落实 Green Candidate Protocol 到当前 PR #9。
4. #17 `QA-HARDEN-2`：建立 Windows CI / latest-SHA checks，最迟在 RF-01 前完成。
5. PR #9 的新 candidate 必须完成两次连续 Development IncludeE2E + launcher + isolated smoke，之后才允许创建新的 formal acceptance。
6. RF-00 #11 在 PR #9 最终处理前保持 OPEN；RF-01 继续阻塞。
