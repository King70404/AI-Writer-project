# M1 Project基础能力正式验收报告

## 验收记录

- 任务：DEV-1.10——M1 Project基础能力正式验收、基线清单与冻结标签
- 验收时间（UTC）：2026-07-26T13:55:38Z
- 验收时间（Asia/Shanghai）：2026-07-26T21:55:38+08:00
- 验收源实现提交：`460307f172776cd718103db1bb4f32067f673d6f`
- 验收源实现树：`7870090cc9bc55e0968a000f1b191046ffba069b`
- 验收前提交数：21
- 验收前跟踪文件数：343
- 正式结果：通过

本报告的测试数、覆盖率、运行时版本、Git对象和依赖审计结果均来自本次实际复验。验收只读取源实现提交和隔离测试资源，没有修改生产代码、测试、依赖、Schema、Alembic迁移或前21个提交，也没有访问正式用户数据。

## 正式验收结论

M1 Project基础能力正式验收通过。

该结论代表Project从不可变领域模型、事务持久化、应用用例、HTTP API到React前端及修订历史形成真实可验证闭环，不代表Story Bible、规划、章节写作、审核、Canon、Codex、Agent或完整AI网文产品已经完成。

## M0基线保护

- M0标签：`m0-engineering-foundation`
- 标签类型：annotated tag（Git对象类型`tag`）
- 标签对象：`a017a9167aefe09b6ee4026a20dac4cc4ce33780`
- 标签目标：`a9a3a6ff361a610aac6ef66a98deed60efccd715`
- 三份M0冻结文件相对M0标签无差异。
- 验收未移动、覆盖、删除或重建M0标签，未改写任何M0历史事实。

## M1验收范围

### 领域和数据基础

已验收Prefixed ULID、aware UTC时间、`RevisionNumber`、`ConcurrencyVersion`、通用`ConcurrencyConflict`、`Project`、不可变`ProjectRevision`、独立`ProjectHead`、一致`ProjectAggregate`、不可变领域转换，以及`ProjectTitle`和`ProjectDescription`规则。

### 持久化和事务

已验收`projects`、`project_revisions`、`project_heads`三表，复合Head所有权外键、RevisionNumber唯一约束、双不可变触发器、原子创建、一致当前聚合读取、Revision追加、Project CAS、Head CAS、并发冲突、失败回滚和损坏拒绝。

### 应用层

已验收创建与完整修订命令、当前Project查询、Project列表查询、Revision历史列表、单Revision读取、脱离ORM/Web的Snapshot和Page，以及应用服务到专用Repository/Reader端口的单次调用边界。

### HTTP API

已验收Project创建、当前读取、完整修订、稳定Keyset列表、Revision历史Keyset列表、单Revision读取、强ETag、`If-Match`、412冲突、安全错误映射、未迁移数据库503和生产OpenAPI关闭。

### React前端

已验收Project列表、创建、稳定加载更多、当前详情、强ETag完整修订、显式412冲突恢复、只读不可变Revision历史、按需正文、未知路由404、内存CSRF以及无写请求自动重试。

## 功能真实性

M1正式功能ID精确为：

1. `PRJ-001`：Project创建API；
2. `PRJ-002`：当前Project读取API；
3. `PRJ-003`：Project完整修订API；
4. `PRJ-004`：Project列表API；
5. `PRJ-005`：Project列表与创建前端流程；
6. `PRJ-006`：Project详情与修订前端流程；
7. `PRJ-007`：Project不可变修订历史查看。

没有增加`PRJ-008`或其他M1功能编号。

## 当前真实用户能力

当前用户可以通过真实前后端和SQLite持久化链路创建Project、查看Project列表、稳定加载更多、查看当前详情、完整修订Project、显式处理并发冲突、查看不可变Revision历史并按需读取单Revision标题与简介。

Project的`description`是Project简介，不是章节正文编辑器。当前不支持小说正文创作。

## 数据库Schema验收

- Alembic唯一head：`0002_create_project_foundation`。
- 正式Metadata精确为：`project_heads`、`project_revisions`、`projects`。
- 当前迁移文件仅有`0001_initialize_database.py`和`0002_create_project_foundation.py`，不存在0003。
- 独立临时数据库实际完成`0001 → 0002 → 0001 → 0002`循环。
- 0002阶段精确创建三张Project表、命名索引`ix_project_revisions_project_id_revision_number`、复合Head所有权外键和两个Revision触发器。
- 降级至0001后Project表、索引和触发器全部删除；重新升级后完整重建。
- 迁移不插入示例Project或业务数据。
- SQLite WAL和外键启用；验收不访问默认开发数据库或正式LocalAppData数据根。

## Revision不可变性

数据库触发器`trg_project_revisions_no_update`和`trg_project_revisions_no_delete`分别拒绝直接SQL及ORM的Revision UPDATE和DELETE。失败不会改变既有Revision正文；历史正文仍由不可变Revision拥有，Head只决定当前指针。

## Repository事务验收

Project专项552项测试实际通过，覆盖：

- 原子创建以及Revision或Head晚期失败的完整回滚；
- 当前聚合单次一致读取；
- Revision追加、Project CAS和Head CAS；
- stale版本在时钟、ID生成和写SQL之前快速拒绝；
- Revision插入、Project CAS、Head CAS和commit失败的完整回滚；
- 每次操作独立Session，并在成功与失败路径关闭；
- Head缺失、目标Revision缺失、所有权错误、非法领域值和非法时间关系的安全损坏拒绝；
- 错误不泄漏SQL、数据库路径、标题或简介正文。

## 并发验收

两个独立Repository实例在同一临时SQLite文件上以相同expected version并发写入时，恰好一个成功、另一个得到`ConcurrencyConflict`。实现使用`BEGIN IMMEDIATE`与数据库CAS，不使用全局Python锁、sleep排序、自动重试、自动合并或覆盖。

## 应用层验收

创建与修订输入在可观测副作用前验证；一个写命令只对应一个Repository写事务。应用层不打开Session、不执行SQL、不导入SQLAlchemy或Web层。当前读取、列表和历史查询各自只调用对应端口一次，不通过写Repository进行N次读取。

## HTTP与ETag验收

POST、GET和PUT的强ETag精确表达`ConcurrencyVersion`。PUT必须提供规范`If-Match`，缺失返回428，非法返回400，stale由Repository CAS裁决并返回412；服务不预读、自动重试、自动合并或覆盖。

Project列表按`created_at DESC, project_id DESC`使用Keyset；Revision历史按`revision_number DESC`使用绑定Project的Keyset。两个cursor均严格版本化、非授权凭据、非跨请求快照，不返回total或OFFSET语义。

## Production API路由

生产API精确为9条：

1. `GET /api/v1/health/live`
2. `GET /api/v1/health/ready`
3. `GET /api/v1/security/session`
4. `GET /api/v1/projects`
5. `POST /api/v1/projects`
6. `GET /api/v1/projects/{project_id}`
7. `PUT /api/v1/projects/{project_id}`
8. `GET /api/v1/projects/{project_id}/revisions`
9. `GET /api/v1/projects/{project_id}/revisions/{revision_number}`

不存在其他业务API；production的`/docs`、`/redoc`和`/openapi.json`关闭。

## 前端路由

前端路由精确为：

1. `/`
2. `/projects`
3. `/projects/:projectId`
4. `/projects/:projectId/history`
5. `*`

## 前端真实链路

`/projects`使用真实列表和创建API；创建成功后重新读取第一页，部分成功状态不会重发POST。详情GET把严格响应和强ETag绑定为内存编辑基线；PUT只发送一次。412保留草稿，只有用户显式读取最新版本并选择采用或重建基线后才能再次手动保存。历史页按需读取正文，不自动加载全部Revision。

## 安全边界验收

- POST和PUT继承Host、Origin、本地Session、CSRF、JSON内容类型和正文大小限制。
- Project及历史GET不要求Session或CSRF，但保持Host验证、安全响应头和`Cache-Control: no-store`。
- CSRF、Cookie、ETag、cursor、草稿和Revision正文不进入日志、URL或浏览器持久存储。
- 不安全写请求没有自动重试；错误响应不泄漏SQL、路径、Cookie、令牌或正文。
- 安全静态、架构、运行测试及14项E2E全部通过。

## 依赖安全验收

- Node.js：`24.18.0`
- npm：`11.16.0`
- React：`19.2.7`
- React DOM：`19.2.7`
- React Router：精确`8.3.0`
- Vite：`8.1.4`
- `react-router-dom`不存在。
- `npm ls`无invalid或extraneous。
- `npm audit --omit=dev`实际结果为0个生产漏洞。
- 未增加依赖、审计忽略规则或锁文件变化。

## 运行时版本

| 运行时或库 | 本次实际版本 |
| --- | --- |
| Python | 3.12.10 |
| SQLite | 3.49.1 |
| FastAPI | 0.139.0 |
| SQLAlchemy | 2.0.51 |
| Alembic | 1.18.5 |
| Node.js | 24.18.0 |
| npm | 11.16.0 |
| React | 19.2.7 |
| React DOM | 19.2.7 |
| React Router | 8.3.0 |
| Vite | 8.1.4 |

## 完整质量门禁

本次从干净源实现基线实际执行并全部通过：

1. `.\scripts\quality_gate.ps1`
2. `.\scripts\quality_gate.ps1 -IncludeE2E`
3. `.\scripts\quality_gate.ps1 -IncludeDependencyAudit -IncludeE2E`

没有降低阈值、跳过测试、排除失败场景或修改门禁。

## 后端测试与覆盖率

- 完整pytest与架构测试：1116项通过。
- 后端语句覆盖率：94.41%。
- 后端分支覆盖率：87.50%。
- Project专项：552项通过。
- Ruff格式、Ruff规则、mypy、pip check、架构与安全门禁全部通过。

## 前端测试与覆盖率

- Vitest：28个文件、215项测试全部通过。
- Statements：96.67%。
- Branches：92.94%。
- Functions：99.55%。
- Lines：96.64%。
- Prettier、ESLint、TypeScript和Vite production build全部通过。

## E2E结果

14个现有场景全部通过：`E2E-DEV-001`至`E2E-DEV-003`、`E2E-INT-001`至`E2E-INT-010`、`E2E-STARTUP-001`。真实链路覆盖工程基础、路由隔离、安全基线、Project API、列表、创建、详情修订、显式412冲突、不可变历史、20+1分页、production直接刷新和缺失构建失败。

E2E使用受控环回端口和独立临时数据根；外部网络被阻止，成功后端口、进程、数据库、WAL、SHM、journal、运行目录和Playwright成功产物均清理。

## 临时资源清理

- 临时SQLite、WAL、SHM和journal残留：0。
- 迁移测试数据根残留：0。
- E2E运行根和编排目录残留：0。
- Playwright成功产物残留：0。
- 临时Manifest生成脚本和验收日志：0。
- 本任务拥有的Python/Node服务残留：0。
- E2E专用端口全部释放。
- 覆盖率临时JSON未被Git跟踪。
- 正式默认数据根和默认开发数据库未访问。

## 架构边界结论

Project继续唯一拥有三张Project表；领域层保持标准库边界；应用层不依赖Web或持久化实现；Project Web不访问SQLAlchemy、Session或具体Reader；只有持久化适配层执行SQL；`main`是唯一组合根。UI不访问SQLite，Workflow和CodexRuntime仍未进入M1。

## M1明确未完成范围

以下内容未实现，也不属于M1完成范围：Story Bible、世界观、角色卡、力量体系、大纲、卷规划、章节规划、章节正文编辑、Review、Canon、Style、Analytics、Workflow、Character、Chapter、三区隔离、分支、审批、Revision回滚/恢复/Diff/编辑、Project删除/归档/恢复、CodexExecutor、Codex生成、Agent、Skill、Prompt管理、AI小说生成、安装器、CI/CD、云同步和多用户账号。

## 已知非阻断风险

1. FastAPI/Starlette TestClient仍产生上游`httpx`迁移弃用警告；当前锁定依赖兼容且所有测试通过。
2. Python 3.12在两项受控SQLite损坏测试中报告默认datetime adapter弃用警告；不影响当前数据正确性，后续依赖维护任务应显式迁移适配方式。
3. 当前只提供本机HTTP和进程内临时Session，不是用户登录或企业身份方案。
4. Keyset cursor不代表跨请求数据库快照；这是已记录并测试的当前契约。
5. 当前没有备份恢复、单实例锁或全面Windows ACL治理，必须在相应后续阶段独立实现和验收。

以上风险不阻断M1，但不得在后续里程碑中隐去或弱化。

## M1冻结政策

`m1-project-foundation`是历史冻结annotated tag，消息固定为`M1 project foundation accepted`。标签创建后不得移动、覆盖、强制重建或删除；本报告、`M1_ACCEPTANCE_CHECKLIST.md`和`M1_BASELINE_MANIFEST.json`不得改写。

后续里程碑可以通过新任务和新提交扩展Project，但不得改写M1历史事实。未来发现M1缺陷时，必须创建新编号任务和新提交，不得amend、rebase或重写M1验收提交。M0标签继续永久保留。Manifest中的源实现树与M1标签共同构成可重现证据：前者固定验收前实现，后者固定包含验收文档的完整验收提交。

## M2进入边界

M1验收完成只满足进入下一阶段的工程前提，不自动授权任何M2功能。Story Bible、Planning、Writing、Character、Chapter、Canon、Codex、Agent等能力必须由后续独立编号任务明确授权。

## 最终声明

M1 Project基础能力正式验收通过。

该结论代表Project从不可变领域模型、事务持久化、应用用例、HTTP API到React前端及修订历史形成真实可验证闭环，不代表Story Bible、规划、章节写作、审核、Canon、Codex、Agent或完整AI网文产品已经完成。
