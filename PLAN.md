# AIWebNovel project continuity plan

本文件是跨 ChatGPT 对话、Codex 本地执行与 GitHub 审阅之间的项目接力页。它记录“已经做过什么、现在卡在哪里、下一步做什么”。

开始任何项目任务前，先读取最新 GitHub 状态、根目录 `AGENTS.md`、本 `PLAN.md`，再读取当前活动 Issue / PR。若本文件与 GitHub 当前 Issue、PR、已通过验收报告冲突，以 `AGENTS.md` 中的优先级为准，并先同步本文件的状态。

## 当前阶段

当前仍处于 **RF-00：锁定重构基线**，不得开始 RF-01 或 RF-03+ 开发。

在 RF-00 内插入 QA 稳定化阶段，原因是 V1-UX-1 已连续两次在 formal acceptance 中暴露此前未被 Development 完整预检发现的 blocker。新的目标是让 formal acceptance 只复核已经反复绿过的冻结 SHA，而不是继续承担“第一次完整发现问题”的职责。

重构总路线保持：

`RF-00 基线 → RF-01 产品规格/模块契约 → RF-02 测试契约 → RF-03 场景 → RF-04 Story Assets → RF-05 Skills → RF-06 Model Gateway/API Key → RF-07 ContextPack → RF-08 单段任务 → RF-09 安全采纳 → RF-10 200–300 字连续生成 → RF-11 Story Memory → RF-12 一致性评审 → RF-13 跨章召回/失效 → RF-14 作者工作台 → RF-15 升级备份恢复 → RF-16 长篇评测 → RF-17 发布验收`。

旧的 `V1-AI-1` 不再作为当前下一任务直接启动；云端模型/API Key 能力纳入 RF-06。

## 已完成的重要历史

- M0–M7 / V1 已完成并冻结；M0–M7 tag 与历史验收文件不可移动、不可改写。
- V1-OPS-1R 已完成正式恢复验收。
- TXT 导出浏览器差异已通过独立 Playwright/Chromium 交叉验证，未发现产品导出缺陷。
- DOC-GOV-1 已完成，根 `AGENTS.md` 已明确 GitHub 唯一事实源、任务自主性、formal hard-stop、数据根与冻结边界。
- V1-UX-1 PR #9 已形成，但尚未通过 formal acceptance，也尚未合并。
- Issue #10 / V1-UX-1-Q1：formal FAIL，首个 blocker 为 E2E-INT-009 `书名` / `确认书名` locator 歧义。
- Issue #12 / V1-UX-1-R1：Development recovery PASS；生成候选 `553d28988fe1c182cbb95fffe50965a7391879d8`。
- Issue #14 / V1-UX-1-Q2：formal FAIL。`quality_gate.ps1 -IncludeE2E` 在 frontend coverage 阶段失败；`tests/frontend/novel-structure-workspace.test.tsx` 的 `loads an empty workspace, avoids invalid Chapter reads, and creates each level` 超过 Vitest 5000ms 默认 timeout（5068ms），同一运行出现 `Received NaN for the value attribute`。正式 Playwright E2E、launcher smoke、isolated author smoke 均未进入。

## 当前活动工作

### RF-00 — Issue #11

目标：锁定唯一、可验证的最终 `main` 重构起点。PR #9 与 QA hardening 完成前保持 OPEN。

### V1-UX-1 — Issue #8 / PR #9

PR #9 尚未合并。最近失败 formal candidate：

`553d28988fe1c182cbb95fffe50965a7391879d8`

该 SHA 不再允许直接进入新的 formal acceptance；必须先经过新的 Green Candidate Protocol。

### QA-HARDEN-1 — Issue #15

目标：停止“修一个 blocker → 立刻再开正式验收”的打地鼠流程。

正式规则已写入：

- `docs/ACCEPTANCE_STABILITY.md`
- `AGENTS.md` Green Candidate 入口条件

新的 formal acceptance 只能针对已经在 Development / RC preflight 中证明稳定的精确 SHA。

### V1-UX-1-R2 — Issue #16

当前唯一允许的下一代码恢复任务。

目标：

- 修复 novel-structure number input 清空时 `valueAsNumber -> NaN` 进入受控 `value` 的非法中间状态；
- 消除 React `Received NaN for the value attribute` warning，而不是静音 warning；
- 拆分/优化当前接近 5 秒上限的 mega-test，保持语义覆盖，不提高 timeout；
- 精确失败测试修复后独立稳定运行至少 20 次；
- 所属测试文件独立稳定运行至少 5 次；
- full frontend coverage + Default gate PASS。

### QA-HARDEN-2 — Issue #17

在 RF-01 之前必须完成 GitHub-visible Windows CI / latest-SHA checks：

- PR 更新自动跑 Default gate；
- merge-ready / RC 跑 IncludeE2E；
- 失败保留日志/产物；
- CI 只用隔离数据；
- main 最终配置 required status checks / up-to-date rule（若管理权限需要仓库 owner 操作，则明确记录 owner action）。

## 为什么之前会反复失败

当前证据显示不是同一个 bug 反复出现，而是多个类别的问题被推迟到 formal acceptance 才首次完整暴露：

1. UI 文案变化后 locator 未系统审计，出现 substring accessible-name 歧义；
2. Recovery 只跑窄范围 + Default，没有让完整 IncludeE2E 在 Development 阶段先跑绿；
3. 存在一个包含多个独立业务步骤的大型 jsdom 单测，大量 `userEvent.type`，运行时间已经靠近 Vitest 默认 5000ms 边界；
4. React warning 没被当作候选 blocker，导致 `NaN` 非法受控输入状态被带进 formal；
5. GitHub 当前没有 server-side required CI / branch protection，最新 SHA 的完整测试证据主要靠人工复制本地结果；
6. PR #9 规模较大、提交历史长，增加了交互回归面。

## 新的 Green Candidate Protocol

完整规则见 `docs/ACCEPTANCE_STABILITY.md`。

在新的 formal acceptance Issue 创建前，精确 candidate SHA 至少必须：

1. Default gate PASS；
2. `quality_gate.ps1 -IncludeE2E` 在 Development / RC-preflight 模式下对同一未修改 SHA 连续 PASS 两次；
3. Windows launcher smoke PASS；
4. 隔离 author UX/delete smoke PASS；
5. 已知 timing-sensitive 测试完成重复稳定性验证；
6. 无未解释 React warning / console error / pageerror / requestfailed；
7. Git / migration / tag / frozen history / formal data 边界全部干净。

候选有任何新 commit，连续绿色计数清零。

## 下一步顺序

1. 完成 #16 / V1-UX-1-R2 Development recovery。
2. 继续 #15 / QA-HARDEN-1，把 Green Candidate preflight 落到 PR #9 实际候选。
3. 完成 #17 / QA-HARDEN-2 的 Windows CI / latest-SHA checks；最迟必须在 RF-01 前完成。
4. 对最终 PR #9 candidate 执行 RC preflight：Default → IncludeE2E #1 → IncludeE2E #2 → launcher smoke → isolated author smoke。
5. 只有上述全部 PASS 且 SHA 冻结后，才创建新的 formal acceptance Issue。
6. formal PASS 后才允许合并 PR #9、关闭 V1-UX-1，并在 RF-00 #11 记录最终 main SHA。
7. RF-00 关闭后才开始 RF-01。

## 当前禁止事项

- 不合并 PR #9。
- 不创建新的 formal acceptance，直到 Green Candidate Protocol 满足。
- 不通过提高 timeout、sleep、retry、skip、降低 coverage、删除测试或弱化断言解决稳定性问题。
- 不开始 RF-01、RF-03+ 或 RF-06 Model Gateway。
- 不开始旧 V1-AI-1 旁路任务。
- 不移动 M0–M7 tags，不改写冻结验收历史。
- 不用正式 `%LOCALAPPDATA%\AIWebNovel` 数据做测试/Smoke。

## RC 协调冻结规则

在最终 RC preflight 开始前，先同步本文件与活动 Issue/PR。RC preflight 开始后，不再仅为了状态说明向 `main` 追加协调 commit；动态状态写入当前 Issue/PR。candidate PASS/FAIL 后再同步 `PLAN.md`，避免纯文档 commit 使冻结 candidate 无故落后于 base。

## 接力维护规则

每当出现以下事件，当前负责人必须同步本文件：

- 新编号任务开始或完成；
- PR 创建、合并、关闭或 candidate SHA 改变；
- formal acceptance PASS / FAIL；
- 新 blocker 或 recovery task；
- QA preflight / CI 策略变化；
- `main` 基线被正式锁定或改变；
- 下一任务顺序发生改变；
- 重要产品/架构方向被批准并写入 GitHub。

不要把聊天记录当作项目状态库；重要事实进入 GitHub Issue、PR、`PLAN.md` 或正式文档。不得在这些文档中记录 API Key、密码、Cookie、令牌、私钥或作者正式创作内容。
