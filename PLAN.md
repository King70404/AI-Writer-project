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
- #18 / V1-UX-1-RC1：Green Candidate FAIL。冻结候选 `00e569740f880510d54a0c2ef8c90746f984602a` 的 Default PASS，首次 IncludeE2E 在 INT-012 陈旧 Story Bible 标题断言处失败；后续第二次完整门及两项 smoke 未运行。失败证据保留于 [#18 结果](https://github.com/King70404/AI-Writer-project/issues/18#issuecomment-5646556594)，不重跑该轮。

## 当前活动工作

### RF-00 — #11

目标：最终记录一个唯一、可验证的 `main` SHA 作为重构起点。

在 PR #9 完成 Green Candidate、formal acceptance、merge 之前，RF-00 保持 OPEN；RF-01 保持 blocked。

### V1-UX-1 — #8 / PR #9

PR #9 仍 OPEN、未合并。R2 已完成，但 **Development recovery PASS 不等于 merge readiness**。

本次 R3 开始时 GitHub PR #9 head：

`00e569740f880510d54a0c2ef8c90746f984602a`

GitHub `main` 为 `0939e3a0a753dc819ab0f5bc6f4496198c3290dd`，已包含在该候选中。RC1 已失败。R3 已修复测试契约，但补充作者验证发现 #20 的真实产品缺口；完成 R4 后才能独立进入 RC2。不能把开发检查或 RC1 的部分通过当成 Green Candidate PASS。

### QA-HARDEN-1 — #15

Green Candidate 规则已写入：

- `AGENTS.md`
- `docs/ACCEPTANCE_STABILITY.md`

新的 formal acceptance 不能再成为第一次完整运行；必须先由新的 RC 轮对同一个冻结 SHA 完成完整 preflight。

### V1-UX-1-R3 — [#19](https://github.com/King70404/AI-Writer-project/issues/19)

**Development recovery PASS，#19 已关闭 completed。** 已正常推送提交 `ce435479e99658325f9660205fa6fe22c8760075` 到 PR #9 原分支；完整证据见 [R3 结果](https://github.com/King70404/AI-Writer-project/issues/19#issuecomment-5658478079)。

模式：Development recovery，不是 RC1 重跑或 formal acceptance。

本任务范围：

1. 保留 RC1 screenshot、trace 和错误上下文，再执行新的开发测试。
2. 修复 INT-012 与已批准作者界面的陈旧文案/定位契约，检查创建、编辑、冲突、持久化等后续断言。
3. 审查 PR #9 其余受影响 E2E，修复可证实的同类问题；保留行为、ETag、请求次数和浏览器安全审计。
4. 独立运行 INT-012、相关场景、完整浏览器集与 Default gate；开发失败在本范围内诊断修复，不冒充 RC/formal 证据。
5. 同步开发证据，核对 migration、冻结历史、tag 和隔离数据清理，再交接新的精确候选。

实际结果：INT-012 独立 PASS；完整浏览器集 24/24 PASS（真实 exit 0）；Default PASS（真实 exit 0），后端 2776、前端 55 文件 / 676 测试。后端覆盖率 statements 97.45%、branches 93.65%；前端 statements 96.08%、branches 92.06%、functions 98.91%、lines 96.62%。保留 5 条已知后端依赖弃用警告及 Playwright 的颜色环境变量提示；没有观察到对应 React warning。迁移、冻结历史和 tag 未变化，测试自有端口和数据已清理。

### V1-UX-1-R4 — [#20](https://github.com/King70404/AI-Writer-project/issues/20)

**开发修复与规定开发检查 PASS；GitHub Issue 收尾待同步。** 从已同步的 R3 提交 `ce435479e99658325f9660205fa6fe22c8760075` 开始；模式为 Development recovery。完整证据见 [R4 开发报告](docs/V1-UX-1-R4_DEVELOPMENT_REPORT.md)。R3 补充作者 smoke 未宣告 PASS，发现进入新 RC 前应解决的问题：

- 删除临时小说后，旧 Character history 页面仍能列出修订并打开角色档案；其他已检查普通详情及 Project/Story Bible 历史入口已拒绝访问。修复必须关闭普通读取路径，同时保留不可变历史。
- R4 真实迁移数据库红测进一步证实 Story Bible 历史 API 也有相同遗漏：两个模块的列表、旧 cursor 页及旧/当前修订正文共 8 条路径在删除后仍返回 200。此前设定历史页面的 404 来自前置当前状态读取，不能作为其历史 API 已封闭的证据；R4 同时修复两个历史状态查询。
- 设定与人物普通页面仍展示内部 ID / 并发信息。#8 对隐藏元数据的显式范围是 Project 详情（已满足），#18 的普通作者 smoke 范围更广；R4 明确补齐子页展示及同一路径中文化，不伪造过去验收事实。

真实浏览器已确认文本 autocomplete 为 off；卷序号清空被拒绝、重新输入可保存；删除要求精确书名。第一次补充 smoke 因会话中断触发自有期限并清理；续跑使用全新隔离根完成上述观察后清理。临时验证脚本的整张修订表相等检查不适用于会追加删除标记修订的逻辑删除，不能据此声称历史改写或历史完整性已验证；R4 回归需逐条比较删除前已存在的修订。

R4 最终结果（2026-09-15）：两个历史 reader 已修复；数据库回归验证删除后 8 条历史路径 404、旧记录逐条不变；作者页面隐藏内部元数据并同步中文文案。Default 真实 exit 0，后端 2778 / 前端 676 PASS；完整浏览器 24/24 PASS；已知 structure 测试完成独立 20+5 次稳定性验证。此前 Windows 应用程序控制导致依赖加载失败的开发证据保留；续跑时环境恢复，未修改安全策略，完整门已通过。

当前协调 blocker：GitHub connector 的 Issue/PR 接口返回 transport error，#20 尚未关闭，RC2 Issue 尚未创建；Git heads 读取正常，先把 R4 代码、报告和本接力页同步到 PR 原分支。恢复后先补发 R4 结果并结束 #20，再记录独立 RC2。8 个本地冻结 tag 未变化；远端 tag 查询 exit 0 但返回空清单，尚不能声称远端冻结标签已核验，不擅自补推标签。

### 新 RC / formal 入口

R4 完成后再记录独立 RC2，先同步协调记录、锁定新候选与 GitHub head/base。冻结 SHA 上依次要求：

`git diff --check / clean → Default PASS → IncludeE2E PASS #1 → IncludeE2E PASS #2 → isolated launcher smoke → isolated author UX/delete smoke → migration/tag/frozen-history/Git clean`。

launcher smoke 必须实际走根目录 `启动 AI 网文助手.cmd`，但启动该 `.cmd` 的进程需把 `LOCALAPPDATA` 临时覆盖到任务自有的仓库外目录，使无参数 launcher 的默认 `AIWebNovel` 数据根落在隔离位置；不得读取或枚举作者真实 `%LOCALAPPDATA%\AIWebNovel`。

RC2 PASS 后才能创建绑定该 SHA 的新 formal acceptance；正式门失败须保留证据并停止该轮，经新的恢复任务后再修改候选。旧 #18 FAIL 保持不变。

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

1. #19 / R3 已完成；#20 / R4 开发检查已通过，先恢复 Issue/PR 协调并同步结果，再交接新的候选。
2. 创建独立 RC2 并完成 Green Candidate preflight；PASS 后重新读取 GitHub，创建绑定该精确 SHA 的新 formal acceptance Issue。
3. 新 formal acceptance PASS 后，才允许合并 PR #9、关闭 V1-UX-1，并在 #11 记录最终 `main` SHA。
4. 完成 #17 Windows CI / latest-SHA checks；required repository rule 按实际 GitHub 套餐/owner 权限落地或记录唯一管理限制。
5. PR #9 处理完成且 #17 满足 RF-01 前置条件后，关闭 RF-00。
6. RF-00 关闭后才开始 RF-01。

## 当前禁止事项

- 不重跑旧 #18；不直接重开 formal acceptance，先完成 R4 和新的 Green Candidate。
- 不合并 PR #9。
- 不在 RC validation 内顺手修产品；失败必须形成新的 recovery task。
- 不通过 timeout inflation、sleep、retry、skip、降低 coverage、删除测试、静音 warning 或弱化断言制造绿色。
- 不开始 RF-01、RF-03+ 或 RF-06。
- 不开始旧 V1-AI-1 旁路任务。
- 不移动 M0–M7 tags，不改写冻结验收历史。
- 测试 / E2E / smoke 不得访问作者真实 `%LOCALAPPDATA%\AIWebNovel`。

## RC 协调冻结规则

R3 是 RC1 失败后的独立恢复，不再受旧候选冻结期间的文件禁止修改约束。新的 RC preflight 前先同步本文件与活动 Issue/PR，再冻结新 candidate。preflight 进行期间不再仅为了状态说明向 `main` 追加协调 commit；动态结果写入新的 RC Issue / PR #9。candidate PASS/FAIL 后再同步本文件。

## 接力维护规则

以下事件发生后必须同步本文件或对应 Issue/PR：新任务开始/完成、candidate SHA 改变、formal PASS/FAIL、新 blocker、QA/CI 策略变化、PR merge/close、最终 RF-00 baseline 改变。

不要把聊天记录当项目状态库；重要事实进入 GitHub。不得在协调文档中记录 API Key、密码、Cookie、令牌、私钥或作者正式创作内容。
