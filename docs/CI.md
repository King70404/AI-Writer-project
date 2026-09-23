# Windows CI

工作流为 `.github/workflows/windows-quality.yml`（Windows Quality），只使用 GitHub 托管的 `windows-2022` 临时 runner。它执行仓库原有门禁，不调整测试、覆盖率、超时或浏览器重试。

| 触发                                 | 固定检查名          | 实际执行                                                                                 |
| ------------------------------------ | ------------------- | ---------------------------------------------------------------------------------------- |
| 每次 PR 创建、更新、重开或转为 ready | `Windows Default`   | `scripts/quality_gate.ps1`                                                               |
| 同一次 PR 事件                       | `Windows Full`      | `scripts/quality_gate.ps1 -IncludeE2E`，包含完整 Development / Integrated E2E 与清理验证 |
| 任意分支 push（不监听 tag）          | `Windows Default`   | 默认门禁                                                                                 |
| 手动 `Full`                          | `Windows Full`      | IncludeE2E 完整门禁                                                                      |
| 手动 `Stability`                     | `Windows Stability` | 已知 structure 精确组 20 次、所属文件 5 次                                               |

PR 检查显式 checkout `github.event.pull_request.head.sha`；push / 手动执行使用事件 SHA。开始和结束均校验 HEAD，保留完整 Git 历史，产物记录实际候选 SHA、触发类型和 run attempt。PR 自动运行 Full，因此首次合入 main 前也能获得真实 Full 结果。手动按钮要求工作流已存在于默认分支；手动执行前核实所选分支的当前 SHA，结果只属于实际记录的 SHA。新提交必须重新运行，不能沿用旧日志。

## 环境和隔离

- Python 固定为 **3.12.10 x64**，Node.js 固定为 **24 x64**；Actions 本身固定到不可变 commit SHA。
- `setup-python` 后只在临时 runner 的 HKCU 按 PEP 514 注册该解释器，再验证真实 `py -3.12` 与 `pythonLocation` 指向同一文件。这样诊断脚本仍执行原有精确版本规则。引导脚本拒绝普通本机和 self-hosted runner，不修改作者电脑的 Python 注册。
- 从零创建根 `.venv`，运行 `pip install -e "./backend[dev]"`、`npm ci`；Default / Full 均显式运行 `npm run e2e:install`，因为两种模式的末尾环境诊断都检查 Chromium，且各 job 使用全新浏览器缓存。Default / Full 在质量门前真实运行 `npm run build`，使后端架构测试调用的 Integrated 诊断拥有前端构建产物；质量门本身仍完整运行其前端步骤。前端使用已提交 lockfile；后端沿用现有 pyproject 依赖范围，当前没有独立后端锁文件。
- 每个 job 在 `RUNNER_TEMP` 创建自己的随机目录，显式设置 `TEMP`、`TMP`、`LOCALAPPDATA`、`AIWEBNOVEL_DATA_ROOT` 和外置 Chromium 缓存。E2E 继续使用现有脚本创建、校验、清理的场景独占根。
- token 权限只有 `contents: read`；checkout 不保留凭据。不注入 secrets，不使用 `pull_request_target`，不写分支、tag、release、正式数据库或备份。
- 同一事件分支的新运行会取消旧运行；Default 和 Full 在不同临时机器独立执行，一个失败不会取消另一个的证据收集。任何一个失败都不满足合并条件。

默认和 Full 门禁成功后还执行环境诊断（分别 Development / M0）并检查跟踪文件未变化。任一步失败即停止该 job 后续检查，保留首个 blocker。安装失败也会使 job 失败，不自动重试。

前端边界测试在同一会话中替换内存源码并新增合法样例，因此该测试套件局部设置 `TSESTREE_SINGLE_RUN=false`，结束时恢复环境。否则 `CI=true` 会让 TypeScript 解析器使用不可变的磁盘程序缓存，漏读内存样例并拒绝新文件。此设置只声明动态测试的解析生命周期；生产 ESLint 配置、类型检查、27 个非法样例的精确诊断均保留。排查同类问题时使用 `$env:CI='true'; npm.cmd run quality` 复现 CI 行为，不能仅凭普通本地运行通过判定恢复完成。解析器行为见 [官方说明](https://typescript-eslint.io/packages/parser/#disallowautomaticsingleruninference)。

## 稳定性与产物

手动选择 `Stability` 时运行 `scripts/run_ci_stability.ps1`：

1. `tests/frontend/novel-structure-workspace.test.tsx` 的 `creation behaviors|keeps a cleared position` 精确组独立执行 20 次；当前每次命中 8 项。
2. 同文件独立执行 5 次；当前每次 17 项。

每轮保存文本与 JSON 报告，检查非零退出、非空测试选择、失败数量及 stderr / React warning 等非预期诊断；首次失败即停止，不补跑、不覆盖旧输出。固定 20+5 是稳定性验证次数，不是失败重试。具备依赖的本机也可以把 `-OutputDirectory` 指向新的自有临时目录运行这个独立脚本；它不注册 Python、不启动产品服务、不访问正式数据。

每个 job 始终尝试上传 `windows-<mode>-<sha>-<attempt>`，保留 14 天：完整执行 transcript、`run.json` 首个 blocker、环境诊断、稳定性逐轮报告、前端覆盖率摘要，以及原 E2E 保留的失败 HTML / trace / screenshot。运行早于引导脚本失败时，以 GitHub job 日志为准。不会上传整个临时数据根、SQLite、模型或备份；E2E 自有运行根清理后，现有脚本输出的有限服务诊断保留在 transcript。

## Required checks 与验收边界

仓库 owner 应在 main 的 branch protection / ruleset 中要求 `Windows Default` 和 `Windows Full`，来源选择 GitHub Actions，并启用 **Require branches to be up to date before merging**。必须核对最新 PR head 的两项检查都成功。若权限或套餐阻止设置，活动 Issue #17 必须记录具体 API 结果、缺少的能力及 owner 待办；工作流文件本身不代表规则已启用。

CI 是开发证据。单次 Full 不能替代同一冻结 SHA 连续两次 IncludeE2E、真实根 launcher、隔离作者 smoke、边界复核和独立 formal acceptance。完整流程仍按 [稳定性协议](ACCEPTANCE_STABILITY.md) 执行，未正式 PASS 不合并 PR #9。

参考：[GitHub PR 事件与 head SHA](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request)、[手动执行条件](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch)、[Python Windows 注册规范](https://peps.python.org/pep-0514/)。
