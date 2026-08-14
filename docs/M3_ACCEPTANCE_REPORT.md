# M3 Character 基础能力验收报告

## 验收结论

M3 在 M0 工程底座、M1 Project 基础能力与 M2 Story Bible 基础能力之上，完成了 Character 的稳定对象、不可变修订、事务持久化、应用用例、HTTP 接口、前端创建/编辑流程与只读历史闭环。本次验收只冻结已经存在并通过正式门禁的能力，不把诊断工具、测试稳定化或未来路线登记为产品功能。

## 实现基线

- implementation HEAD：`8864938d1389f9900299f5dc7095d7a1f9f058b9`
- implementation tree：`27a3a29950e1d365dac87822366965db9aaa0012`
- implementation commit count：40
- tracked files：598
- branch：`main`
- Git remote：无

M3 的 11 个实现提交依次为：

1. `3f438b771ea0f88084041f889aac549f73dd6ebb` — `feat(character): establish immutable revision model`
2. `7212e51500409974f774ee7bec66a217983ed608` — `feat(character): add transactional persistence`
3. `dad7c90a68f27d64a3cf8857782dc60bfe2e60a3` — `feat(character): add application use cases`
4. `844def3dc634f7a290b62d006311058679954b06` — `test: stabilize repository quality gates`
5. `4fab9fd19ba9f96e36b982d57fdef50b5116d3e7` — `feat(character): expose HTTP API`
6. `b80c2cbcac9b9a4ae8ffdb3e004f66c4ff40e714` — `feat(frontend): add character editing flow`
7. `2d99ff7643f67e956da2515eaa3bbd2643e966e0` — `feat(character): add immutable revision history`
8. `6678504489ebc0d2c85ea1a2297627ca58b80af7` — `test: stabilize frontend coverage determinism`
9. `6a82832e8cba98788e01b435877ebc9e15b5abbb` — `test: stabilize eslint boundary gate performance`
10. `23b1476b9d1b9a90569175248b34d459f367f04f` — `test: stabilize project revision history e2e`
11. `8864938d1389f9900299f5dc7095d7a1f9f058b9` — `test: stabilize project frontend health audit`

## 冻结能力

Character 采用 stable object + immutable revisions + head authority。事务 Repository、应用命令与查询、显式 Snapshot 映射、强 ETag 与乐观并发已经建立。HTTP 层支持按 Project 创建与列表、按 Character ID 读取与完整替换，并提供只读修订列表和单修订详情。

前端支持 Project 内 Character 列表、创建、编辑、冲突显式恢复及不可变历史查看。历史列表只返回摘要，不返回完整 profile；历史详情按需返回完整 historical profile。历史 Keyset cursor 严格绑定 Character，Head 是当前 Revision 的唯一权威，历史 Revision 不可变。

继承能力保持不变：Project 的创建、读取、完整修订、稳定列表、前端创建/编辑与不可变历史；Story Bible 的本地 HTTP API、纯文本创建/修订前端与不可变历史。Feature Reality Matrix 精确冻结 `PRJ-001` 至 `PRJ-007`、`STB-001` 至 `STB-003`、`CHR-001` 至 `CHR-003`，没有新增虚构 Feature ID。

## 正式质量证据

文档创建前与三份文档暂存后分别独立执行 Default、IncludeE2E、DependencyAudit+IncludeE2E，共六次正式质量门，均以真实退出码 0 完成且没有失败重跑。

- 后端：2268 项通过；statements 96.85%，branches 92.57%。
- 前端：43 个测试文件、473 项测试通过；statements `2369 / 2469`（95.94%），branches `2308 / 2525`（91.4%），functions `539 / 544`（99.08%），lines `2328 / 2416`（96.35%），coverage files 90。
- ESLint 受控非法样例：27；timeout 15000ms；12 个 carrier groups；1 个 ESLint instance；1 次 `calculateConfigForFile`；1 个 Linter instance；12 次 verify；fixture disk writes 0。forward、reverse、fixed rotation 三种顺序均得到 27 个样例与 43 条规范化诊断，规则、消息和位置精确一致，mismatch、fatal、parser error、syntax error 均为 0。
- E2E：development-state 3、integration 16、missing-build-state 1，共 20；四次正式 IncludeE2E 套件均为 20/20。`E2E-INT-008`、`E2E-INT-010`、`E2E-INT-014`、`E2E-INT-015`、`E2E-INT-016` 均通过。
- 两次 npm 生产依赖审计均为 0 漏洞；React Router 为 8.3.0。

## Production API 库存

实际 production OpenAPI 重新生成后精确为 21 operations：

- `GET /api/v1/health/live`
- `GET /api/v1/health/ready`
- `GET /api/v1/projects`
- `POST /api/v1/projects`
- `GET /api/v1/projects/{project_id}`
- `PUT /api/v1/projects/{project_id}`
- `GET /api/v1/projects/{project_id}/revisions`
- `GET /api/v1/projects/{project_id}/revisions/{revision_number}`
- `GET /api/v1/projects/{project_id}/story-bible`
- `POST /api/v1/projects/{project_id}/story-bible`
- `GET /api/v1/security/session`
- `GET /api/v1/story-bibles/{story_bible_id}`
- `PUT /api/v1/story-bibles/{story_bible_id}`
- `GET /api/v1/story-bibles/{story_bible_id}/revisions`
- `GET /api/v1/story-bibles/{story_bible_id}/revisions/{revision_number}`
- `GET /api/v1/projects/{project_id}/characters`
- `POST /api/v1/projects/{project_id}/characters`
- `GET /api/v1/characters/{character_id}`
- `PUT /api/v1/characters/{character_id}`
- `GET /api/v1/characters/{character_id}/revisions`
- `GET /api/v1/characters/{character_id}/revisions/{revision_number}`

Character rollback、restore、history write、historical delete/adopt、delete 和 archive 均不在 production OpenAPI；即使未注册写入方法得到 405，也不计入库存。

## 前端路由库存

带 path 的 production 路由精确为 10 条：

- `/`
- `/projects`
- `/projects/:projectId`
- `/projects/:projectId/history`
- `/projects/:projectId/story-bible`
- `/projects/:projectId/story-bible/history`
- `/projects/:projectId/characters`
- `/projects/:projectId/characters/:characterId`
- `/projects/:projectId/characters/:characterId/history`
- `*`

无 path 的布局 Route 不额外计数。

## 数据库冻结

正式 Metadata 精确为 9 表：`character_heads`、`character_revisions`、`characters`、`project_heads`、`project_revisions`、`projects`、`story_bible_heads`、`story_bible_revisions`、`story_bibles`。Alembic head 为 `0004_create_character_foundation`，不存在 0005。

迁移 Git blob 冻结为：

- 0001：`63112b9b7d4510decb9b38de07ceb867491f2e05`
- 0002：`5aa10200b7290278000cc21951850960dc914089`
- 0003：`deb9c9c05fa2af8dd78c701c1afe72fb26b7fc99`
- 0004：`175044bfad61a4595000e4ec3dc01c5db6b3e641`

独立迁移 SQLite 的实际库存确认 6 个 Revision 不可变触发器：Project、Story Bible、Character 各自的 no-update 与 no-delete。SQLite 使用 WAL 并启用 foreign keys。

## 测试稳定化与历史观察

Q8 是质量测试稳定化，不是新产品能力。`E2E-INT-010` 曾以非唯一 Project 标题作为详情页 ready 条件，可能尚停留在 `/projects` 列表便开始编辑。稳定化改为等待精确 Project 详情 URL、`.project-edit` 可见及详情编辑器输入状态正确，同时保留 revision heading 的 `toBeFocused()` 断言，没有删除或弱化焦点语义。

Q10 同样是测试生命周期/browser audit 的稳定化，不是产品逻辑修复。`E2E-INT-008` 快速离开“工程基础”页面时，组件卸载会取消 `GET /api/v1/health/ready`，浏览器报告 `net::ERR_ABORTED`；测试明确声明这一条预期取消，并继续约束 method、path、error 与数量。该稳定化只修改 `tests/e2e/integrated/project-frontend.spec.ts`，未修改产品代码、support helper、runner、quality gate、timeout、worker、browser，也未增加 retry 或 sleep。历史验证包括 standalone 30/30、Project INT-006 至 INT-010 组 10/10、五轮完整 E2E 20/20，以及后续正式门通过。

历史正式门曾两次在 `E2E-DEV-001` 启动并显示单 worker 后，无 Playwright 结果地由外层退出 1。该观察分类仍是 H / 未定位 / 当前未复现 / 未证明已修复。后续多组真实 Default→IncludeE2E 与 Audit+E2E 中均产生真实 PASS，因此当前没有可复现失败，不构成本次冻结阻断。

最终稳定组之前，未修改的 Story Bible conflict flow 曾两次出现约 5 秒 concurrent timeout；后续完整 coverage 与正式质量门未复现。没有修改 Story Bible 产品代码、测试逻辑或 timeout，没有增加 sleep 或 retry；当前没有可复现失败，不宣称 timeout 已修复，若再次出现应保留现场诊断。

正式恢复过程中使用过仓库外进程级诊断确认质量门真实执行与退出传播；Raw process observer、ASCII gate host 与 Unicode environment block 未加入仓库或生产代码，不是 M3 产品能力或生产 runtime。

## 安全、隐私与架构

系统继续采用 local-first、single-user 与 `127.0.0.1` 本地绑定；数据存放于本地 SQLite。没有云 API key、真实 secret、云凭据、遥测、Git remote、push 或新增云服务。写请求继续受本地 Session、CSRF 与可信 Origin 保护；生产 docs/OpenAPI 入口保持关闭，未迁移数据库不会自动迁移。

技术边界保持为 Python 3.12.10、FastAPI、SQLite、SQLAlchemy 2、Alembic 的模块化单体后端，以及 React、TypeScript、Vite、React Router 8.3.0 前端；Node 24.18.0、npm 11.16.0。领域对象采用 prefixed ULID、stable object + immutable revisions + head 与 optimistic concurrency。

## M3 明确范围边界

以下均为 scope boundary / unimplemented，而不是本次验收通过的功能：Character delete/archive/restore/diff/rollback；任何 historical Character write/delete/adopt；Character relationships；World、Location、Organization、Power systems、Abilities、Items；structured age、structured gender、alignment；Avatar、Attachments、Markdown/rich text；Outline、Volume、Chapter；AI generation、Agent systems、Skills、Prompt systems；Autosave、browser draft persistence；0004 之后的迁移；cloud APIs、remote Git integration、release 与 publishing。M4 及后续阶段没有在本次任务中启动。

M3 Character基础能力验收通过。
