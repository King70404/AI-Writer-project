# M1 Project基础能力正式验收清单

本清单记录DEV-1.10对固定源实现提交`460307f172776cd718103db1bb4f32067f673d6f`的正式验收结果。所有勾选项均由本次命令、自动测试、隔离数据库、浏览器E2E、Git对象或[M1正式验收报告](M1_ACCEPTANCE_REPORT.md)支持；不存在跳过项。

## Git与冻结基线

- [x] 当前分支为`main`，执行前工作区干净。
- [x] 执行前HEAD精确为`460307f172776cd718103db1bb4f32067f673d6f`。
- [x] 执行前提交总数为21，最新信息为`feat(project): add immutable revision history`。
- [x] Git remote为空，未推送代码或标签。
- [x] `m0-engineering-foundation`为annotated tag，对象为`a017a9167aefe09b6ee4026a20dac4cc4ce33780`，目标为`a9a3a6ff361a610aac6ef66a98deed60efccd715`。
- [x] 三份M0冻结文件相对M0标签无差异。
- [x] 执行前不存在`m1-project-foundation`，未覆盖未知标签。
- [x] 前21个提交未被amend、rebase、reset或其他方式改写。

## M1范围与领域不变量

- [x] M1范围仅覆盖Project基础，不包含Story Bible、Planning、Writing或其他M2能力。
- [x] Prefixed ULID、aware UTC时间、RevisionNumber与ConcurrencyVersion边界通过。
- [x] Project、ProjectRevision、ProjectHead与ProjectAggregate不变量通过。
- [x] ProjectTitle与ProjectDescription的类型、长度和空白规则通过。
- [x] 不可变领域转换、时钟回退拒绝和stale副作用顺序通过。
- [x] 功能ID精确为`PRJ-001`至`PRJ-007`，没有新增PRJ-008。

## Schema与Migration

- [x] Alembic唯一head为`0002_create_project_foundation`，不存在0003。
- [x] Metadata精确为`project_heads`、`project_revisions`、`projects`。
- [x] 独立临时库完成`0001 → 0002 → 0001 → 0002`。
- [x] 三表、命名索引、主键、唯一约束和复合Head所有权外键通过。
- [x] `trg_project_revisions_no_update`和`trg_project_revisions_no_delete`存在且有效。
- [x] downgrade删除全部M1 Schema，re-upgrade可完整重建且无示例数据。
- [x] SQLite WAL和Foreign Keys启用；未访问正式用户数据库。

## Repository、事务与并发

- [x] 原子Project创建和晚期失败完整回滚通过。
- [x] 当前聚合一致读取及损坏状态拒绝通过。
- [x] Revision追加、Project CAS和Head CAS通过。
- [x] stale请求快速拒绝且不调用时钟、ID工厂或写SQL。
- [x] Revision插入、Project CAS、Head CAS和commit失败均完整回滚。
- [x] 两个并发写恰好一个成功、一个`ConcurrencyConflict`。
- [x] Revision UPDATE和DELETE被数据库触发器拒绝，历史正文不变。
- [x] 每次操作独立Session，成功与失败路径均关闭。

## 应用与HTTP边界

- [x] 创建、修订、当前读取、列表和历史应用服务边界通过。
- [x] 应用层不打开Session、不执行SQL、不依赖Web或持久化实现。
- [x] Production API精确为9条，不存在其他业务API。
- [x] 强ETag、规范`If-Match`、428/400/412语义通过。
- [x] Project列表Keyset cursor、排序、无total/offset语义通过。
- [x] Revision历史Project绑定cursor、降序分页和按需正文通过。
- [x] 未迁移数据库安全返回503，production OpenAPI关闭。
- [x] Host、Origin、Session、CSRF、请求限制与安全错误隐私边界通过。

## React前端与真实用户链路

- [x] 前端路由精确为`/`、`/projects`、`/projects/:projectId`、`/projects/:projectId/history`、`*`。
- [x] Project列表、稳定加载更多和创建后第一页刷新通过。
- [x] Project详情GET、强ETag基线和一次完整替换PUT通过。
- [x] 412保留草稿、显式读取最新、采用或重建基线流程通过。
- [x] Revision历史降序、加载更多、按需单Revision正文和直接刷新通过。
- [x] CSRF、ETag、cursor、草稿和Revision正文未进入浏览器持久存储。
- [x] POST和PUT无自动重试；不存在回滚、恢复、历史编辑或Diff按钮。
- [x] 未知前端路由返回真实404。

## 依赖、质量与清理

- [x] React Router精确为`8.3.0`，不存在`react-router-dom`。
- [x] `npm ls`无invalid或extraneous，生产依赖审计为0个漏洞。
- [x] Project专项552项通过。
- [x] 完整后端与架构测试1116项通过，语句94.41%、分支87.50%。
- [x] 前端28个文件、215项测试通过，四项覆盖率均超过门槛。
- [x] 14项E2E全部通过，包含Project API、列表、详情冲突和Revision历史真实链路。
- [x] 默认、IncludeE2E、依赖审计及E2E三种质量门禁全部通过。
- [x] Ruff、mypy、Prettier、ESLint、TypeScript、Vite、pip check、架构和安全门禁通过。
- [x] 临时数据库、WAL、SHM、journal、测试根、E2E根、Playwright成功产物和自有服务全部清理。
- [x] 未修改生产代码、测试、依赖、锁文件、Schema、迁移或质量门脚本。
- [x] 未新增未来功能，未访问正式LocalAppData数据，未添加remote或推送。

## Manifest与封板

- [x] `M1_BASELINE_MANIFEST.json`为UTF-8、LF、有效JSON和2空格缩进。
- [x] Manifest的implementation commit、tree、21个提交和343个源实现文件准确。
- [x] 343个path按字典序排列、无重复，每个blob OID与源提交逐项一致。
- [x] Manifest精确记录三表、0002 head、9条后端路由、5条前端路由和PRJ-001至PRJ-007。
- [x] Manifest不含绝对本机路径、秘密、临时目录、缓存或M1验收提交新增文件。
- [x] M1验收提交只包含验收文档和必要状态说明，固定信息为`docs(m1): accept project foundation`。
- [x] M1标签创建使用annotated tag `m1-project-foundation`，固定消息为`M1 project foundation accepted`，目标为本清单所在的M1验收提交。
- [x] 标签创建后工作区干净、提交总数22、无remote，三份M1冻结文件相对标签无差异。

## 冻结与后续边界

M1标签和三份M1验收文件均为历史冻结证据，不得移动、覆盖、删除或改写。未来缺陷必须通过新编号任务和新提交修复；后续里程碑不得改写M1历史事实。M1通过只满足M2工程前提，不授权任何Story Bible、规划、章节写作、审核、Canon、Codex或Agent功能。
