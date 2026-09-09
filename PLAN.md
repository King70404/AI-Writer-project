# AIWebNovel project continuity plan

本文件是跨 ChatGPT 对话、Codex 本地执行与 GitHub 审阅之间的项目接力页。它记录“已经做过什么、现在卡在哪里、下一步做什么”。

开始任何项目任务前，先读取最新 GitHub 状态、根目录 `AGENTS.md`、本 `PLAN.md`，再读取当前活动 Issue / PR。若本文件与 GitHub 当前 Issue、PR、已通过验收报告冲突，以 `AGENTS.md` 中的优先级为准，并先同步本文件的状态。

## 当前阶段

当前处于 **RF-00：锁定重构基线**，不得开始 RF-01 或 RF-03+ 开发。

重构总路线来自已批准的《AIWebNovel 重构总设计与执行路线 v1.0（提案）》：

`RF-00 基线 → RF-01 产品规格/模块契约 → RF-02 测试契约 → RF-03 场景 → RF-04 Story Assets → RF-05 Skills → RF-06 Model Gateway/API Key → RF-07 ContextPack → RF-08 单段任务 → RF-09 安全采纳 → RF-10 200–300 字连续生成 → RF-11 Story Memory → RF-12 一致性评审 → RF-13 跨章召回/失效 → RF-14 作者工作台 → RF-15 升级备份恢复 → RF-16 长篇评测 → RF-17 发布验收`。

旧的 `V1-AI-1` 不再作为当前下一任务直接启动；云端模型/API Key 能力纳入 RF-06，必须在 RF-00～RF-05 的前置契约与资料/Skills 基础完成后实施。

## 已完成的重要历史

- M0–M7 / V1 已完成并冻结；M0–M7 tag 与历史验收文件不可移动、不可改写。
- V1-OPS-1R 已完成正式恢复验收。
- TXT 导出浏览器差异已通过独立 Playwright/Chromium 交叉验证，未发现产品导出缺陷。
- DOC-GOV-1 已完成，根 `AGENTS.md` 已明确 GitHub 唯一事实源、任务自主性、正式验收 hard-stop、数据根与冻结边界。
- V1-UX-1 开发候选已形成 PR #9；候选 `5cb13a549d46d53c2bfc1d166d980ef750e5d112` 的 Default Quality Gate 已通过，但这不等于正式验收通过。
- V1-UX-1-Q1（Issue #10）已完成一次 formal acceptance，结果为 FAIL，并已关闭作为失败验收记录。

## 当前活动工作

### RF-00 — Issue #11

目标：在任何重构开发之前锁定唯一、可验证的 `main` 起点。

当前产品代码基线快照（RF-00 建立时）：

`main = 286a106d9805c07ef3c6825b6ef58811ee910103`

协调/计划文档可能在 RF-00 期间继续追加到 `main`；任何执行者必须重新读取 GitHub 当前 `main`，不要把上述快照当作永远不变的分支头。

### V1-UX-1 — Issue #8 / PR #9

PR #9 失败验收候选：

`5cb13a549d46d53c2bfc1d166d980ef750e5d112`

主要内容：

- 普通作者界面隐藏内部 Project / Revision / concurrency 工程字段；
- 作者化中文术语；
- 创作表单 autocomplete 抑制；
- 安全“删除小说”逻辑删除；
- Windows 双击启动器；
- 相关测试与文档同步。

PR #9 尚未合并。

Issue #12 的 locator-only recovery 与 Development 验证已完成。新的 candidate 为本次恢复提交后的 UX 分支 HEAD；精确 SHA 与执行证据记录在 [PR #9](https://github.com/King70404/AI-Writer-project/pull/9) 和 [Issue #12](https://github.com/King70404/AI-Writer-project/issues/12)，不能继续使用上述失败候选作为当前候选。

### 已失败的正式验收 — Issue #10（已关闭）

`V1-UX-1-Q1` 在精确候选 `5cb13a549d46d53c2bfc1d166d980ef750e5d112` 上执行 formal `IncludeE2E` 时失败，并按 hard-stop 停止。

首个真实 blocker：

`tests/e2e/integrated/project-detail-edit.spec.ts` 的 E2E-INT-009 使用：

`getByRole("textbox", { name: "书名" })`

在项目详情页同时匹配“书名”和“确认书名”，触发 Playwright strict mode violation。不是 timeout，不允许通过增加等待、retry、skip 或降低断言解决。

正式验收没有继续执行 Windows launcher smoke 或 isolated author UX/delete smoke，因此这些项目仍未验收。

## 当前恢复状态与下一验收入口

**Issue #12 — `V1-UX-1-R1`：Development recovery 完成，等待新一轮 formal acceptance。**

- 已将协调 main `21edc508a02ee72591451b7650ec0396d5453ac0` 正常合入 UX 分支；merge commit 为 `c875edf670a7f732acf65964c1fe9b7c6ced8e50`，没有 rebase 或历史重写。
- 仅修改 E2E-INT-009：四处详情页“书名”输入框使用 `exact: true`；返回列表后的书名断言限定到“项目列表”中的精确标题，避免导航期间匹配详情页与删除确认说明中的同名文本。
- 首次 Development 专项越过原输入框 blocker 后，在返回列表的书名断言发现上述同名文本歧义（exit 1）；完成 locator-only 修正后，E2E-INT-009 PASS（exit 0）。
- 直接相关 E2E-INT-008、E2E-INT-010 均 PASS（exit 0）；未修改其他 spec、生产代码、API、Schema、迁移、timeout、retry 或 browser audit。
- Default Quality Gate PASS（exit 0）：后端 2776 项，statements 97.45%、branches 93.65%；前端 55 文件 / 666 项，statements 96.02%、branches 91.97%、functions 99.05%、lines 96.65%。
- 未运行新的 Formal IncludeE2E，未执行 Windows launcher 或隔离 author UX/delete 正式 Smoke，未合并 PR #9。

当前 blocker 不再是 Issue #12 开发恢复，而是新 candidate 尚待新的 formal acceptance Issue 验收。下一步由 ChatGPT 创建该 Issue；旧 #10 仍保留为失败历史，不重新使用。

## 下一步顺序

1. Issue #12 / V1-UX-1-R1 开发修复与规定开发检查已完成；以 PR #9 / Issue #12 回写的新 candidate SHA 接力。
2. ChatGPT 重新读取 GitHub，确认 PR #9 最新 HEAD 与 recovery 执行记录一致。
3. 由 ChatGPT 创建绑定新 SHA 的 formal acceptance Issue；不要重开或重跑已经失败的 #10 作为同一轮验收。
4. 新正式验收必须重新运行规定的 `IncludeE2E`，随后执行 Windows launcher smoke 与隔离 author UX/delete smoke。
5. 若新候选 PASS：ChatGPT 重新读取 GitHub，按既有授权合并 PR #9，关闭 V1-UX-1 相关 Issue，并在 RF-00 #11 记录最终 merge 后 `main` 作为重构起点。
6. 只有 RF-00 关闭后才能开始 RF-01。
7. RF-01 完成并验收后才按 RF 路线逐项继续；不一次性开发 RF-03～RF-17。

## 当前禁止事项

- 不合并尚未通过 formal acceptance 的 PR #9。
- 不开始 RF-01、RF-03+ 或 RF-06 Model Gateway。
- 不开始旧 `V1-AI-1` 旁路任务。
- 不移动 M0–M7 tags，不改写冻结验收历史。
- 不用正式 `%LOCALAPPDATA%\AIWebNovel` 数据做测试/Smoke。
- 不在 formal acceptance 失败后直接修改候选并在同一验收任务里重跑。

## 接力维护规则

每当出现以下事件，当前负责人必须同步更新本文件：

- 新编号任务开始或完成；
- PR 创建、合并、关闭或 candidate SHA 改变；
- formal acceptance PASS / FAIL；
- 新 blocker 或 recovery task；
- `main` 基线被正式锁定或改变；
- 下一任务顺序发生改变；
- 重要产品/架构方向被批准并写入 GitHub。

不要把聊天记录当作项目状态库；聊天里产生的重要事实必须进入 GitHub Issue、PR、`PLAN.md` 或相应正式文档。不要在本文件记录密码、API Key、Cookie、私钥或作者正式创作内容。
