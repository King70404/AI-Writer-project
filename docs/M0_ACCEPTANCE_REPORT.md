# M0工程底座正式验收报告

## 验收记录

- 任务：DEV-0.11——M0正式阶段验收与工程基线冻结
- 验收时间：2026-07-18T17:58:55+08:00
- 本地时区：Asia/Shanghai（UTC+08:00）
- 候选基线：`f8490124c3aff841e1c0263bfd193343fdc3782d chore(dev): establish startup and diagnostics`
- 候选提交数：11
- 正式结果：通过

所有证据均来自本次对固定候选基线的实际复验、只读审计和隔离烟测，不以DEV-0.10报告作为唯一证据。正式验收没有修改运行时代码、脚本、测试、依赖、数据库配置或既有提交。

## 验收范围

本次验收覆盖阶段0的仓库治理、Python与FastAPI后端基础、SQLite与Alembic基线、React与TypeScript前端基础、本地前后端集成、质量门禁、Chromium E2E、本地存储、安全中间件、Environment Doctor、统一启动、清理机制和功能真实性边界。

不在本次范围内的内容包括阶段1、小说项目与版本对象、人物、章节、规划、写作、评审、Canon、Codex接入、Agent、Skill、Prompt、持久工作流、备份恢复、安装器、Windows服务、CI、远程仓库和产品发布。验收过程未创建、读取、枚举、迁移或删除正式用户小说数据。

## 候选基线正式复验

五项规定命令均在HEAD仍为候选提交、工作区干净时实际执行并返回退出码0。

| 复验命令 | 开始时间（UTC+08:00） | 结束时间（UTC+08:00） | 持续时间 | 退出码 | 测试数量 | 覆盖率 | E2E | 依赖审计 | 清理结果 |
| --- | --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| `environment_doctor.ps1 -Mode M0` | 2026-07-18 17:36:03.724 | 2026-07-18 17:36:11.642 | 7,917 ms | 0 | 不适用 | 不适用 | 不适用 | 不适用 | 诊断临时根清理通过；ENV-001至ENV-012全部通过，结论为ready |
| 默认质量门禁 | 2026-07-18 17:36:19.631 | 2026-07-18 17:37:48.100 | 88,469 ms | 0 | 后端与架构374；前端29 | 后端90.72%/82.12%；前端88.95%/82.11%/97.82%/88.82% | 不适用（未请求） | 不适用（未请求） | 未启动长期服务；仓库卫生与安全静态基线通过 |
| IncludeE2E质量门禁 | 2026-07-18 17:37:55.777 | 2026-07-18 17:41:08.592 | 192,815 ms | 0 | 后端与架构374；前端29 | 后端90.72%/82.12%；前端88.95%/82.11%/97.82%/88.82% | 9项通过 | 不适用（未请求） | 自有进程、端口、数据根与数据库sidecar清理通过 |
| 依赖审计及E2E质量门禁 | 2026-07-18 17:41:20.726 | 2026-07-18 17:44:24.053 | 183,327 ms | 0 | 后端与架构374；前端29 | 后端90.72%/82.12%；前端88.95%/82.11%/97.82%/88.82% | 9项通过 | npm生产依赖0个漏洞 | 自有进程、端口、数据根与数据库sidecar清理通过 |
| `m0_preflight.ps1` | 2026-07-18 17:44:57.990 | 2026-07-18 17:50:21.203 | 323,213 ms | 0 | 后端与架构374；前端29 | 后端90.72%/82.12%；前端88.95%/82.11%/97.82%/88.82% | 9项通过 | npm生产依赖0个漏洞 | M0-001至M0-009全部通过，临时产物清理通过并保留两份忽略报告 |

M0预验收报告生成时间为`2026-07-18T09:50:21Z`，其原始结论保持为“`M0预验收检查通过，等待正式阶段验收。`”。该预验收结论未被改写为正式结论。

## 环境与工具版本

| 工具 | 实际版本或结果 |
| --- | --- |
| Git | 2.55.0.windows.2 |
| PowerShell | 5.1.26100.8875 |
| Python Launcher选择结果 | Python 3.12.10 |
| 项目虚拟环境Python | Python 3.12.10，64位 |
| pip | 26.1.2 |
| SQLite | 3.49.1 |
| Ruff | 0.15.21 |
| mypy | 1.20.2 |
| pytest | 9.1.1 |
| Node.js | v24.18.0，x64 |
| npm | 11.16.0 |
| React | 19.2.7 |
| TypeScript | 6.0.3 |
| Vite | 8.1.4 |
| Playwright | 1.61.1 |
| Chromium | 149.0.7827.55，Playwright revision 1228 |

Playwright仅要求并实际使用Chromium；本地浏览器清单还包含Chromium headless shell及其辅助组件，不包含Firefox或WebKit。Playwright浏览器缓存位于仓库之外。工具版本与锁文件和当前开发依赖兼容，所有正式门禁均据此通过。

## Git历史与完整性

- `git fsck --full`退出码为0，没有对象损坏或缺失。
- 候选历史为一个根提交加十个单父提交，共11个提交；merge commit数量为0。
- 分支为`main`，候选工作区干净，无remote、无标签，既有提交未被改写。
- 完整性检查发现52个dangling blob和4个dangling tree，但没有dangling commit或tag。这是不阻断M0的本地Git卫生观察，不影响可达历史完整性；遵循任务要求未执行垃圾回收或历史压缩。

候选基线的11个提交按时间顺序为：

1. `d18fe18 chore: establish repository governance baseline`
2. `398a9b4 chore: enforce repository line endings`
3. `2a2d39f feat(backend): initialize FastAPI service`
4. `bdf9ff3 feat(backend): establish database foundation`
5. `bd129bb feat(frontend): initialize React application`
6. `e74d6bd feat(app): integrate frontend and backend`
7. `9365eff chore(quality): establish local quality gates`
8. `890d53b test(e2e): establish browser acceptance tests`
9. `7626b71 feat(storage): establish local data directories`
10. `a5ff2c1 feat(security): establish local application safeguards`
11. `f849012 chore(dev): establish startup and diagnostics`

## 工程基础结果

### 后端基础

后端生产包实际只有`core`、`db`、`diagnostics`、`security`、`storage`、`web`和`main`组合根。FastAPI应用工厂、类型化配置、请求ID、统一错误结构、会话生命周期和关闭时数据库引擎释放均由正式测试验证。ready实际检查configuration、application、storage、database、security及frontend，live与ready语义保持分离；应用不会自动迁移业务数据库。

生产API实际枚举结果仅为：

- `GET /api/v1/health/live`
- `GET /api/v1/health/ready`
- `GET /api/v1/security/session`

生产环境的`/docs`、`/redoc`和`/openapi.json`关闭。开发或测试环境可启用框架文档路由；静态前端与受限SPA回退不构成业务API。不存在Project、Chapter、Character、Planning、Writing、Review、Canon、Codex、Agent或Task业务路由，也不存在业务写入方法。

### 数据库与Alembic基线

Alembic唯一head为`0001_initialize_database`。在独立临时数据根实际执行升级后，数据库只包含`alembic_version`，小说业务表、视图、触发器及非自动索引均为0；升级、降级、再升级通过。SQLAlchemy metadata中的业务表数量为0。SQLite的WAL、外键和5,000毫秒busy timeout均由正式测试验证，临时数据库及WAL、SHM、journal在验收后清理。正式数据根和正式数据库未被读取或修改。

### 前端基础

实际客户端路由为：

- `/`：工程基础页`FoundationPage`
- `*`：客户端`NotFoundPage`

React 19基础工程、TypeScript严格配置、Vite生产构建、错误边界、类型化API客户端、SystemStatus真实状态和手动重新检查均通过测试与浏览器验收。开发代理只处理`/api`；生产静态服务与客户端路由回退有效且不会吞掉API。页面没有项目列表、创作工作台、人物、章节、规划或评审页面，没有假统计、假进度、假Agent状态或“开始创作”等无实现操作。

### 功能真实性

功能真实性编号实际且仅有：`FND-001`、`FND-002`、`FND-003`、`FND-004`。这些编号只代表工程基础页、真实本地状态检查、手动重新检查和生产静态服务，不代表小说业务或Codex能力。

## 质量门禁与覆盖率

### 后端

- Ruff格式检查：通过；Ruff静态规则：通过。
- mypy严格类型检查：通过。
- pytest与架构测试：374项通过。
- 语句覆盖率：90.72%，门槛80%。
- 分支覆盖率：82.12%，门槛75%。
- `pip check`、架构边界、仓库卫生和安全静态基线：全部通过。

### 前端

- Prettier、ESLint、TypeScript检查：全部通过。
- Vitest：29项通过。
- statements：88.95%；branches：82.11%；functions：97.82%；lines：88.82%，均达到现有门槛。
- Vite生产构建、npm依赖树：通过。
- npm生产依赖审计：0个漏洞，其中高危与严重漏洞均为0。

本次没有调整覆盖率阈值、排除生产代码或降低任何门禁参数。FastAPI/Starlette TestClient产生既有的非阻断上游弃用警告，未被误报为测试失败。

## 浏览器E2E结果

9个现有场景全部通过：`E2E-DEV-001`至`E2E-DEV-003`、`E2E-INT-001`至`E2E-INT-005`以及`E2E-STARTUP-001`。覆盖开发模式真实状态、手动重新检查、客户端路由、生产集成启动、生产直接客户端路由、API与SPA隔离、刷新稳定性、安全基线和统一启动脚本。

- 浏览器：Chromium 149.0.7827.55，Playwright revision 1228。
- 外部网络：审计夹具仅允许当前场景的环回HTTP/WebSocket，实际意外外部网络请求为0。
- 控制台：意外控制台错误为0；受控本地404/405 HTTP诊断经过明确审查，不作为意外错误隐藏。
- 页面错误：0。
- 残留：本任务拥有的Python/Node进程、E2E端口、临时数据根、SQLite及sidecar均为0。

## 存储结果

- 正式默认根规则保持为`%LOCALAPPDATA%\AIWebNovel`；验收只判断其存在状态，没有创建、枚举、读取、修改或删除其内容。
- 所有诊断、测试和烟测使用唯一隔离临时根；12个标准目录初始化和当前用户创建、读写、删除探针通过。
- 重解析点在创建、遍历和删除前后均检查，发现时安全失败。
- 临时数据库位于隔离根的`data/`，探针、数据库、WAL、SHM和journal全部清理。
- 验收未修改ACL、未提权，也不声称已完成全面Windows ACL审计。

## 安全结果

正式测试和运行烟测确认：服务只允许环回绑定；Host验证有效；不信任代理头；CORS无通配符且不允许凭据型跨站请求；请求体限制与JSON内容类型约束有效；临时本地会话、Cookie属性、CSRF及Origin保护有效；CSRF不进入浏览器持久存储；CSP不含`unsafe-eval`或`unsafe-inline`且生产页面正常；production API文档关闭；日志脱敏canary无泄漏；Server头不泄漏软件版本；ready实际包含`security=ok`。

当前安全边界仍是本地HTTP、无用户登录、无企业身份认证、进程内会话重启失效、无HTTPS证书管理、无LAN访问且无全面ACL治理。这些限制均未被包装成已实现能力。

## 启动与诊断结果

Environment Doctor的Development、Integrated和M0三种模式分别以退出码0通过，ENV-001至ENV-012全部为pass。Development运行耗时7,914毫秒，Integrated运行耗时9,292毫秒；M0正式复验耗时7,917毫秒。JSON输出实际解析通过，路径与秘密扫描通过；Doctor不自动安装、不联网、不修改代码，并具有正确的失败退出码。

Development真实启动确认FastAPI与Vite使用隔离开发数据根、页面ready、手动重新检查有效、受控停止且端口释放；子进程失败路径只清理本任务拥有的进程。Integrated真实启动确认仅启动FastAPI、使用现有dist、production文档关闭、页面ready、使用隔离集成数据根、受控停止且端口释放。M0-001至M0-009九项预验收全部通过，JSON和Markdown报告存在并通过绝对路径与秘密扫描。

## 独立清理结果

验收结束时，本任务启动的Python进程0、Node进程0，标准端口及本次专用端口残留0；Doctor、Startup、E2E、安全和存储受控临时根残留0；临时SQLite、WAL、SHM和journal残留0；工作区中除被允许保留的`.runtime/m0-preflight/`两份忽略报告外没有验收产物。没有按进程名终止用户其他进程，也没有删除正式用户数据。

## 已知风险

| # | 风险 | 是否阻断M0 | 当前缓解措施 | 后续处理阶段 |
| ---: | --- | --- | --- | --- |
| 1 | 当前仍使用本地HTTP | 否 | 只绑定环回，并实施Host、CORS、CSRF、CSP和代理头控制 | 需要远程、LAN或产品发布时建立独立安全任务 |
| 2 | 会话存于进程内存，重启后失效 | 否 | 明确其不是用户登录；Cookie、CSRF、过期和容量行为已测试 | 后续身份与持久会话阶段 |
| 3 | 重解析点检查存在同一用户并发替换的理论TOCTOU窗口 | 否 | 仅操作自有隔离根，操作前后检查重解析点，发现异常即失败且不提权 | 文件、备份或安装能力阶段进一步加固 |
| 4 | 端口探测到实际绑定之间存在极小竞争窗口 | 否 | 只绑定环回；绑定失败即安全退出，不接管未知占用者 | 单实例与启动协调任务 |
| 5 | 静态AST和正则安全门禁不能替代运行时测试 | 否 | 同时采用单元、负向、烟测和浏览器E2E分层验证 | 后续持续增加运行时、模糊与静态分析覆盖 |
| 6 | FastAPI/Starlette TestClient存在非阻断上游弃用警告 | 否 | 当前锁定依赖兼容且374项后端与架构测试通过 | 依赖维护任务跟踪上游迁移 |
| 7 | 当前没有全面Windows ACL治理 | 否 | 当前用户权限探针、重解析点防护和无提权边界已验证，不作过度安全声明 | 文件、备份或安装阶段建立ACL威胁模型 |
| 8 | 当前没有备份和恢复 | 否 | M0没有业务数据，不提供虚假备份入口 | 后续独立备份恢复任务 |
| 9 | 当前没有单实例锁 | 否 | 端口冲突安全失败；使用WAL、busy timeout和严格进程所有权清理 | 正式产品运行或安装阶段前解决 |
| 10 | 当前没有业务数据和业务功能 | 否 | 功能真实性矩阵只登记FND-001至FND-004并明确限制 | 阶段1从独立DEV-1.x任务开始 |

以上十项均不阻断阶段0工程底座验收，但不得在后续阶段被隐去或弱化。

## 冻结的M0基线

本次冻结Python 3.12.10后端、Node.js 24前端开发、FastAPI应用工厂、SQLite/WAL/外键/Alembic、React/TypeScript/Vite、开发与生产集成、LocalAppData存储根规则、安全中间件、质量门禁、Chromium E2E、Environment Doctor、统一启动脚本及功能真实性矩阵。

冻结不表示永远不能修改。后续修改必须具有独立任务编号，说明原因和兼容性影响，重新运行相关门禁，不重写M0标签，也不改写本报告中的历史事实。

## 未完成项与阶段1进入条件

M0验收范围内没有未完成项。所有小说业务、Codex能力以及其他明确排除内容仍未实现，并非验收遗漏。只有验收提交、提交后M0诊断与预验收、annotated标签和最终Git清洁性全部确认后，DEV-1.1的工程前提才成立；阶段1仍须由独立DEV-1.x任务明确授权，当前没有开始。

## 最终结论

M0工程底座正式验收通过。
该结论仅代表阶段0工程底座达到冻结标准，不代表AI网文产品、小说业务能力或Codex能力已经完成。
