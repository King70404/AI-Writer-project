# AIWebNovel project continuity plan

本文件是跨 ChatGPT 对话、Codex 本地执行与 GitHub 审阅之间的项目接力页。它记录“已经做过什么、现在卡在哪里、下一步做什么”。

开始任何项目任务前，先读取最新 GitHub 状态、根目录 `AGENTS.md`、本 `PLAN.md`，再读取当前活动 Issue / PR。若本文件与 GitHub 当前 Issue、PR、已通过验收报告冲突，以 `AGENTS.md` 中的优先级为准，并先同步本文件的状态。

## 当前阶段

当前仍处于 **RF-00：锁定重构基线**。RF-01 及 RF-03+ 均不得开始。

M0–M7 / V1 的正式冻结基线已经成立；当前阻塞不是 V1 基础能力缺失，而是 V1-UX-1 PR #9 尚未完成新的 Green Candidate → formal acceptance → merge 闭环。

当前重构顺序保持：

`RF-00 基线 → RF-01 产品规格/模块契约 → RF-02 测试契约 → RF-03 场景 → RF-04 Story Assets → RF-05 Skills → RF-06 Model Gateway/API Key → RF-07 ContextPack → RF-08 单段任务 → RF-09 安全采纳 → RF-10 200–300 字连续生成 → RF-11 Story Memory → RF-12 一致性评审 → RF-13 跨章召回/失效 → RF-14 作者工作台 → RF-15 升级备份恢复 → RF-16 长篇评测 → RF-17 发布验收`。

旧 `V1-AI-1` 不再作为当前旁路任务；云端模型 / API Key 能力统一进入 RF-06。

## 已完成的重要历史

- M0–M7 / V1 已完成并冻结；M0–M7 tag 与历史验收文件不可移动、不可改写。
- V1-OPS-1R 已完成正式恢复验收。
- TXT 导出浏览器差异已通过独立 Playwright/Chromium 交叉验证，未发现产品导出缺陷。
- DOC-GOV-1 已完成；`AGENTS.md` 已明确 GitHub 唯一事实源、Development / formal 区分、数据根与冻结边界。
- V1-UX-1 PR #9 已形成，但尚未 formal PASS，也尚未合并。
- #10 / V1-UX-1-Q1：formal FAIL，首个 blocker 为 E2E-INT-009 `书名` / `确认书名` locator 歧义。
- #12 / V1-UX-1-R1：Development recovery PASS，生成候选 `553d28988fe1c182cbb95fffe50965a7391879d8`。
- #14 / V1-UX-1-Q2：formal FAIL；frontend coverage 阶段出现 5000ms timeout（5068ms）与 React `Received NaN for the value attribute` warning，formal Playwright / launcher / isolated author smoke 未进入。
- #16 / V1-UX-1-R2：Development recovery PASS，已关闭 completed。代码修复提交 `49620ce9c0ea5f74c549842cb9f11f40f59309fb`；PR #9 在本次协调前 head 为 `956b9e9f63dbd4ef04cad82869967e8b3a57cd86`。目标测试独立 20/20、完整文件 5/5、frontend coverage 与 Default gate 均通过，且无对应 React warning / console.error。
- #13 是未执行的旧 Q2 草案，已关闭 `not_planned`；实际 Q2 formal 历史只保留 #14。

## 当前活动工作

### RF-00 — #11

目标：最终记录一个唯一、可验证的 `main` SHA 作为重构起点。

在 PR #9 完成 Green Candidate、formal acceptance、merge 之前，RF-00 保持 OPEN；RF-01 保持 blocked。

### V1-UX-1 — #8 / PR #9

PR #9 仍 OPEN、未合并。R2 已完成，但 **Development recovery PASS 不等于 merge readiness**。

本次 GitHub 协调前 PR #9 head：

`956b9e9f63dbd4ef04cad82869967e8b3a57cd86`

最终 RC candidate 尚未冻结。#18 开始时必须先重新读取 GitHub，并把最新 `main` 正常同步到 PR #9；同步完成后的新 head 才能作为 Green Candidate 预验收 SHA。

### QA-HARDEN-1 — #15

Green Candidate 规则已写入：

- `AGENTS.md`
- `docs/ACCEPTANCE_STABILITY.md`

新的 formal acceptance 不能再成为第一次完整运行；必须先由 #18 对同一个冻结 SHA 完成完整 RC preflight。

### V1-UX-1-RC1 — #18

**当前唯一下一执行任务。**

模式：Development / RC preflight，不是 formal acceptance。

任务开始顺序：

1. 读取最新 `main`、PR #9、#15、#18、`AGENTS.md`、本 `PLAN.md`、`docs/ACCEPTANCE_STABILITY.md`。
2. 如果 PR #9 落后于最新 `main`，正常 merge 最新 `main` 到 `feat/v1-ux-1-author-usability`；禁止 rebase / 历史重写。
3. 只允许机械处理协调文档同步；出现实质产品/测试冲突则停止，不在该验收任务内修产品。
4. 同步后 push 原 PR 分支，重新读取 GitHub，记录新 head，并冻结为 RC candidate。
5. 冻结后不得再有 source/docs/tests commit；任何新 commit 都使绿色计数清零。

冻结 SHA 上依次要求：

`git diff --check / clean → Default PASS → IncludeE2E PASS #1 → IncludeE2E PASS #2 → isolated launcher smoke → isolated author UX/delete smoke → migration/tag/frozen-history/Git clean`。

launcher smoke 必须实际走根目录 `启动 AI 网文助手.cmd`，但启动该 `.cmd` 的进程需把 `LOCALAPPDATA` 临时覆盖到任务自有的仓库外目录，使无参数 launcher 的默认 `AIWebNovel` 数据根落在隔离位置；不得读取或枚举作者真实 `%LOCALAPPDATA%\AIWebNovel`。

#18 PASS 后停止，由 ChatGPT 重新读取 GitHub 并创建新的 formal acceptance；#18 FAIL 则停止在第一个真实 blocker，由 ChatGPT 创建窄恢复任务。

### QA-HARDEN-2 — #17

Windows GitHub-visible CI / latest-SHA checks 最迟必须在 RF-01 前完成：

- PR 更新自动跑 Default；
- merge-ready / RC 可运行 IncludeE2E；
- 失败保留日志/产物；
- CI 只使用 ephemeral / isolated data；
- 不得把本地手工日志冒充 latest-SHA server-side check。

2026-09-12 GitHub 能力审计：当前私有仓库读取 rulesets API 返回 GitHub `403`，提示需升级 GitHub Pro 或公开仓库才能启用对应能力；当前 integration 也不能读取 branch protection。#17 必须先实现可用 CI，再由仓库 owner 按实际账户/套餐验证 required rules / up-to-date rule 是否可配置。若套餐不支持，应把精确 owner/plan 限制记录为唯一未完成的管理步骤，不能通过降低质量要求或改成公开仓库来“通过”。

## Green Candidate 最低条件

创建新的 formal acceptance Issue 前，冻结 candidate 必须同时满足：

1. Default `scripts/quality_gate.ps1` PASS；
2. 同一未修改 SHA 的 `scripts/quality_gate.ps1 -IncludeE2E` 连续 PASS 两次；
3. Windows launcher smoke PASS；
4. 隔离 author UX/delete smoke PASS；
5. 已知 timing-sensitive 测试已有有效稳定性证据；
6. 无未解释 React warning / `console.error` / `pageerror` / `requestfailed`；
7. Git / migration / tag / frozen history / formal data 边界全部干净。

候选有任何新 commit，连续绿色计数清零。

## 下一步顺序

1. 执行 #18 / V1-UX-1-RC1 Green Candidate preflight。
2. #18 PASS 后，由 ChatGPT 重新读取 GitHub，创建绑定该精确 SHA 的新 formal acceptance Issue。
3. 新 formal acceptance PASS 后，才允许合并 PR #9、关闭 V1-UX-1，并在 #11 记录最终 `main` SHA。
4. 完成 #17 Windows CI / latest-SHA checks；required repository rule 按实际 GitHub 套餐/owner 权限落地或记录唯一管理限制。
5. PR #9 处理完成且 #17 满足 RF-01 前置条件后，关闭 RF-00。
6. RF-00 关闭后才开始 RF-01。

## 当前禁止事项

- 不直接重开 formal acceptance；先完成 #18。
- 不合并 PR #9。
- 不在 RC validation 内顺手修产品；失败必须形成新的 recovery task。
- 不通过 timeout inflation、sleep、retry、skip、降低 coverage、删除测试、静音 warning 或弱化断言制造绿色。
- 不开始 RF-01、RF-03+ 或 RF-06。
- 不开始旧 V1-AI-1 旁路任务。
- 不移动 M0–M7 tags，不改写冻结验收历史。
- 测试 / E2E / smoke 不得访问作者真实 `%LOCALAPPDATA%\AIWebNovel`。

## RC 协调冻结规则

本次更新是 #18 启动前的最后一轮 `main` 状态协调。#18 开始后，先把本 `main` 同步进 PR #9，然后冻结 candidate。preflight 进行期间不再仅为了状态说明向 `main` 追加协调 commit；动态结果写入 #18 / PR #9。candidate PASS/FAIL 后再同步本文件。

## 接力维护规则

以下事件发生后必须同步本文件或对应 Issue/PR：新任务开始/完成、candidate SHA 改变、formal PASS/FAIL、新 blocker、QA/CI 策略变化、PR merge/close、最终 RF-00 baseline 改变。

不要把聊天记录当项目状态库；重要事实进入 GitHub。不得在协调文档中记录 API Key、密码、Cookie、令牌、私钥或作者正式创作内容。
