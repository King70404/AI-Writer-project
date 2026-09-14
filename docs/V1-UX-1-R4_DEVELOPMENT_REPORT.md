# V1-UX-1-R4 Development recovery report

日期：2026-09-15（Asia/Shanghai）。任务：[R4 #20](https://github.com/King70404/AI-Writer-project/issues/20)，所属 [PR #9](https://github.com/King70404/AI-Writer-project/pull/9)。

**开发修复及规定开发检查 PASS；GitHub Issue 收尾待同步。** 本报告不是 Green Candidate 或 formal acceptance 报告。旧 [RC1 #18 FAIL](https://github.com/King70404/AI-Writer-project/issues/18#issuecomment-5646556594) 保持不变。

## 范围与实现

R4 从已推送的 R3 提交 `ce435479e99658325f9660205fa6fe22c8760075` 开始，继续使用 `feat/v1-ux-1-author-usability`。开发期间远端 `main` 为 `0939e3a0a753dc819ab0f5bc6f4496198c3290dd`，已包含在当前分支中。

1. 修复小说删除后仍可直接读取角色和小说设定历史的问题。两个历史 reader 在原状态查询中排除已删除父小说，沿用现有 NotFound 边界。历史列表、旧 cursor 页、旧修订及当前修订正文共 8 条路径，删除前均为 200，删除后均为 404，且不返回 ETag 或测试正文。
2. 保留历史与数据异常语义。真实迁移数据库回归逐条比较删除前已存在记录的 ID 和全部列，仅允许追加一条 Project 删除标记修订。补充父记录缺失的损坏测试，仍须报告 DataCorruption。既有两次 SELECT、Head 权威、keyset 分页及正文延迟读取约束保留。
3. 清理普通作者页面的内部 ID 和并发元数据，包括角色、小说设定和历史详情；保留保存时间、历史版本和冲突处理所需信息。小说设定及同一路径返回链接统一作者中文文案。路由、请求字段、ETag 与乐观并发行为不变。
4. 将回归前移到开发检查。INT-016 保留原有只读浏览器审计，新增另一标签页删除小说、原历史页读取尚未加载修订及旧历史地址被拒绝的验证。数据库检查仍核对 21 条角色修订，并核对旧 Project 修订与新删除标记。其他受影响场景更新可访问名称和隐藏元数据断言；保存版本改由 HTTP 响应、ETag 和下一次保存的并发请求验证。

## 最终开发验证

全部结果均来自实际进程退出码。原始日志和 JSON 结果保存在 Git 忽略的 `.runtime/v1-ux-r4/`；本报告将必要结论同步到仓库，原始日志未作为源码提交。

| 检查                                    | 结果                                    | 证据                                                                                      |
| --------------------------------------- | --------------------------------------- | ----------------------------------------------------------------------------------------- |
| 相关后端及架构回归                      | 156 PASS，26.01 秒                      | 删除、两个历史 persistence/HTTP 与查询边界测试；代理执行结果                              |
| 受影响独立浏览器场景                    | INT-010、012、013、015、016 最终均 PASS | `targeted-e2e-result.json`、`targeted-e2e-2-result.json` 及对应日志                       |
| 完整 `npm run e2e`                      | 24/24 PASS，exit 0                      | `full-e2e.log`、`full-e2e-result.json`；2026-09-14 12:22:54–12:26:00 UTC                  |
| structure 已知不稳定测试                | 目标组独立 20/20、完整文件独立 5/5 PASS | `stability-result.json` 和 25 份独立进程日志；0 unexpected diagnostic，单项测试最长 721ms |
| 最终 Default `scripts/quality_gate.ps1` | PASS，exit 0                            | `default-sept15.log`、`default-sept15-result.json`；2026-09-14 17:19:22–17:26:43 UTC      |
| 最终后端与架构全集                      | 2778 PASS，390.58 秒                    | Default 日志；5 条已有依赖警告                                                            |
| 最终前端全集                            | 55 文件 / 676 PASS，12.96 秒            | Default 日志                                                                              |
| E2E 清理检查                            | PASS                                    | `scripts/check_e2e_cleanup.ps1`：自有端口释放、运行目录及测试数据清理                     |

最终覆盖率：

| 范围     | Statements | Branches | Functions | Lines  |
| -------- | ---------- | -------- | --------- | ------ |
| Backend  | 97.45%     | 93.65%   | —         | —      |
| Frontend | 96.11%     | 92.13%   | 98.91%    | 96.65% |

Default 包括 Git 差异、仓库卫生、安全与启动基线、Ruff、mypy、后端覆盖率阈值、Python 依赖完整性、前端格式/lint/类型/覆盖率/构建以及 Node 依赖完整性检查，全部通过。环境为 64 位 Python 3.12.10、Node 24.18.0；mypy 1.20.2 / librt 0.13.0。

最终测试没有未解释的 React warning、console error、pageerror 或 requestfailed。保留已有 FastAPI/Starlette 和 Python sqlite datetime adapter 弃用警告，以及 Playwright 的 `NO_COLOR` / `FORCE_COLOR` 环境提示。预期 404 仅按确切路径/状态进入既有浏览器 allowlist，没有关闭全局审计。

稳定性目标组每次运行 8 项、名称筛选不选择另外 9 项；完整文件每次运行全部 17 项。未新增 skip，未改动该测试文件。验证对应源码 blob 为 `33c69fd14009838d1e36a5829252c87a8757da31`，测试 blob 为 `d3b2829951d23192d946e8f36d51e731152e21a7`。完整浏览器日志 SHA-256：`46dd5d674c1ce69d7296860a990b6b3bd8749d23e4b607c688c582d7aa7dd3b0`。

上述测试是在 R4 修改后的开发工作树上运行；最终报告和接力页更新不改变受测产品代码。后续 RC 必须重新绑定提交后的精确 SHA，不能把这些开发结果当成该 SHA 已完成两次 IncludeE2E。

## 失败证据与恢复经过

- 首次真实数据库红测证明两个历史模块的 8 条路径在删除后仍为 200；修复两个状态查询后转绿，并补足旧记录逐条不变与父记录损坏回归。
- 开发期格式与旧中文契约断言曾失败，均修正后完成前端全量检查。INT-013 首次因旧标题中的空格失败；trace、截图及上下文先保存到 `int013-development-failure/`，再修正精确 locator 并完成独立及完整浏览器运行。
- 首次 Default 在 mypy 导入 librt DLL 时遭 Windows 应用程序控制阻止，`default-result.json` 保留 exit 1。CodeIntegrity 3077 与该 DLL 对应，安装文件校验与包记录一致；没有修改系统策略、依赖版本或文件信任状态。[Microsoft 的事件说明](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/operations/event-id-explanations) 将 3077 定义为强制策略阻止事件。
- 同期独立后端运行保留 2777 PASS / 1 FAIL：doctor 集成检查返回 2；当时 coverage C tracer 也遭加载阻止。失败日志没有保留完整 doctor 子检查 JSON，因此不把该单项失败的具体原因推定为 mypy。该次运行及其覆盖率不计为 PASS。
- 9 月 15 日继续时，未修改上述依赖或系统配置，mypy 和 coverage tracer 已能加载；原 doctor 单测 1 PASS（12.26 秒），随后完整 Default 2778 / 676 PASS。这里只确认环境恢复及当前结果，不声称由本任务修复了 Windows 安全策略。
- 初版临时稳定性日志审计把测试名中的 “fails safely” / “failures” 误识别为失败，尽管测试进程 exit 0。保留误判日志，仅收紧忽略目录内审计器的 FAIL 单词匹配，再从零完成 20+5 次。产品代码、测试断言、质量门和警告策略未因该误判改动。

## 边界与交接

- 无 migration/schema 修改；M0–M7 冻结验收文件与起点比较无差异。8 个本地冻结 tag 的对象、类型与目标保持一致，没有执行 tag 写入。
- 远端 heads 可通过单次命令级 HTTP/1.1 正常读取。远端 `ls-remote --tags origin` 实际 exit 0 但公布 0 个 tag；这只能证明本轮未取得远端 tag 清单，不能写成“8 个远端 tag 已核验”。需在基线协调中核实其可见性，不擅自推送或重建标签。
- 自动测试只使用自有隔离数据根；未读取、枚举或修改作者正式数据。未添加迁移、放宽 Host/CORS/CSRF、删除测试、提高 timeout、增加测试 retry/sleep、降低覆盖率或静音 warning。
- GitHub connector 当前对 Issue/PR 读写返回 transport error；Git 远端可用。因此本报告和 `PLAN.md` 随 R4 正常提交到 PR 原分支；截至报告编写时，#20 关闭、结果评论及下一 RC Issue 尚未成功同步，不声明这些外部动作已完成。
- 恢复协调入口：读取最新 PR #9、#20 和 main，补发本报告并关闭已完成的 R4 开发任务；记录独立 RC2、同步 `PLAN.md` 与活动 Issue/PR 后冻结新 candidate。该 SHA 依次完成 Default、两次 IncludeE2E、真实根 launcher 隔离 smoke、完整隔离作者 UX/delete smoke 及边界检查，全部通过后才能创建新的 formal acceptance。
- 真实 launcher 与完整人工作者 smoke 尚未在修复后的 RC 候选执行；E2E 通过不代替它们。本轮不合并 PR #9，RF-00 继续 OPEN，#17 Windows CI 仍须在 RF-01 前完成。
