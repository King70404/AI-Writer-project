# M5 Chapter Writing Foundation 验收报告

## 范围与实现基线

DEV-5.3 只验收并冻结现有正文写作能力，不新增功能，不开始 M6。产品链为：Novel Structure Workspace → Chapter「写正文」→ 纯文本编辑 → Autosave → 本地 FastAPI → SQLite 不可变 ChapterRevision。

| 实现身份 | 值 |
| --- | --- |
| implementation HEAD | `0de5193bc6100d1b6d934e8a2aaccdb296e6d52c` |
| implementation Tree | `65cb5463f82b8cee1c2653eba7ca32c3896fd00b` |
| implementation commit count | 49 |
| implementation tracked files | 670（由 Git 实测，不含未跟踪覆盖率文件） |
| branch / staging / remote | main / empty / empty |

M4 之后精确只有两个实现提交：

1. `da382ecadfb706cf860eb4c67e5a3bfc397b6e74` — `feat(chapter-writing): add manuscript content API`。
2. `0de5193bc6100d1b6d934e8a2aaccdb296e6d52c` — `feat(frontend): add chapter writing workspace`。

验收提交仅增加本报告、`docs/M5_BASELINE_MANIFEST.json`、`docs/M5_ACCEPTANCE_CHECKLIST.md`，使提交数成为 50、tracked files 成为 673。提交主题为 `docs(m5): accept chapter writing foundation`；annotated tag 为 `m5-chapter-writing-foundation`，消息为 `M5 chapter writing foundation accepted`，目标为承载这三份文件的验收提交。具体提交与标签对象、三份文档 blob 在执行报告中记录，避免文档自引用哈希。

## Chapter 正文与统一版本

ChapterRevision 的完整业务内容为 `title`、`summary`、`position`、`content`。`ManuscriptContent` 是纯文本，允许空字符串、换行和 Tab，CRLF/CR 规范化为 LF，不 trim，最大 2,000,000 字符；拒绝非字符串、超长输入、其他 C0/C1 控制字符以及 U+2028/U+2029。

结构与正文共享同一个 Chapter stable object、ChapterRevision、head、concurrency_version 和 revision_number；任一更新创建新的完整不可变版本，而不是独立正文版本系统。

- CreateChapter 保持 M4 的 `title/summary/position` 输入合同，Revision 1 的 `content = ""`。
- UpdateChapter 只改结构字段，并复制当前正文；改标题、梗概或位置不会清空正文。
- UpdateChapterContent 完整替换正文，保留标题、梗概、位置、Project 和 Volume 归属。
- Repository 在独立 `BEGIN IMMEDIATE` 事务内检查 stale，再调用 Factory/Clock，插入版本并原子更新 head/version；失败回滚，不自动重试或合并。
- GetChapterContent 读取当前 head 的不可变应用快照；UpdateChapterContent 使用 expected_version。应用层依赖 Repository 契约，stale 保持 ConcurrencyConflict 语义。

## 数据库、迁移与触发器

Metadata 精确 18 张业务表，M5 没有新增表。仅 `chapter_revisions` 新增 `content TEXT NOT NULL`；stable `chapters` 不含 content、body、draft、word_count。完整表名与触发器名见 Manifest。

Alembic head 为 `0006_add_chapter_manuscript_content`，不存在 0007。六份迁移的提交 blob 与工作树 blob 相同：

| 迁移 | Git blob |
| --- | --- |
| 0001 | `63112b9b7d4510decb9b38de07ceb867491f2e05` |
| 0002 | `5aa10200b7290278000cc21951850960dc914089` |
| 0003 | `deb9c9c05fa2af8dd78c701c1afe72fb26b7fc99` |
| 0004 | `175044bfad61a4595000e4ec3dc01c5db6b3e641` |
| 0005 | `2982c22e8406d74b9a913f2b468137484c7490dc` |
| 0006 | `c230b40dbe955ccacbbf246f3596d1ee5cdb63c8` |

正式后端套件中的 `tests/backend/test_novel_structure_migration.py::test_0006_preserves_old_chapter_revisions_across_migration_cycle` 验证：0005 → 0006 upgrade、0006 → 0005 downgrade、0005 → 0006 re-upgrade 全部通过。历史 M4 ChapterRevision 升级后正文为空，原结构字段不变。

12 个 revision 不可变触发器保持不变；M5 没有新增 trigger。ChapterRevision 的 no UPDATE / no DELETE 继续保护 content。独立迁移数据库实测 WAL、外键启用，核验后临时数据库与 sidecar 已清理，没有访问正式创作数据。

## HTTP 与安全协议

真实 production OpenAPI 精确 34 个 method/path。M4 的 32 条全部保留；M5 仅新增：

- `GET /api/v1/chapters/{chapter_id}/content`
- `PUT /api/v1/chapters/{chapter_id}/content`

GET 返回 chapter/project/volume identity、当前 revision identity、revision_number、concurrency_version、content、updated_at、revision_created_at，以及 strong ETag。PUT body 仅为 `content`，要求真实 If-Match；成功返回新快照和 ETag。两者使用 `Cache-Control: no-store`。

缺失 If-Match 返回 428，格式错误返回 400，stale 返回 412，Chapter 不存在返回 404。沿用本地 session/CSRF、Host/Origin、JSON 类型和请求体大小保护；错误响应不泄漏 SQL、SQLite/SQLAlchemy 内部信息、traceback、本机路径或正文。

领域的 200 万字符上限不等于 HTTP 字节上限：现有默认请求体限制仍为 1 MiB（包含 JSON 编码开销），M5 未放宽安全配置。超过限制时安全拒绝并保留编辑区正文。

## 写作工作台与 Autosave

前端精确 12 条 production routes，Manifest 完整枚举。唯一新增路由为 `/projects/:projectId/chapters/:chapterId/write`。Structure Workspace 的 Chapter 提供「写正文」入口；写作页先加载并校验 Project/Chapter/Volume/正文归属，再显示编辑器。

页面提供返回小说结构、章节与卷信息、纯文本 textarea、字符数、保存状态和立即保存，无复杂 IDE 布局。字符数使用 JavaScript `content.length`（UTF-16 code units），不持久化，数据库/API 没有 word_count 或 character_count 字段。

Autosave debounce 为 1000ms。状态为 saved（已保存）、dirty（未保存）、saving（正在保存）、error（保存失败）、conflict（版本冲突）。

- `inFlight` guard 保证同时最多一个正文保存请求。保存期间继续输入时，旧请求完成不会把新输入误报为已保存；新内容仍 dirty，继续安排下一次保存。
- GET 获取真实 ETag，PUT 发送最近确认的 If-Match；成功采用服务端返回的新 ETag，不猜测版本。
- 412 进入 conflict、停止 Autosave、保留本地正文；不自动重试、merge 或重新取 ETag 强制覆盖。用户可明确选择「丢弃本地正文并重新加载服务器版本」。
- 普通网络/5xx 失败进入 error 并保留正文，允许继续编辑和手动重试；无无限 retry。用户再次编辑可触发新的防抖保存。
- 立即保存与编辑区 Ctrl+S 共用同一保存 pipeline；Ctrl+S 调用 preventDefault。
- saved 不注册 beforeunload 提示；dirty/saving/error/conflict 提供浏览器关闭或刷新保护。未实现复杂 SPA 路由阻断，不承诺站内导航前强制保存。
- 卸载时取消 timer、abort 请求并忽略晚到响应。没有 localStorage/IndexedDB/session draft recovery；当前保护链为 Autosave → FastAPI → SQLite。

## 本次正式质量门

两门在创建任何 M5 文档前、同一 implementation HEAD 上各运行一次。Default 通过后才执行 IncludeE2E。未重跑失败门，文档后不再重复完整门。

| 正式命令 | 次数 | 结果 | 真实退出码 |
| --- | --- | --- | --- |
| `.\scripts\quality_gate.ps1` | 1 | PASS | 0 |
| `.\scripts\quality_gate.ps1 -IncludeE2E` | 1 | PASS，E2E 22/22 | 0 |

两门均通过仓库卫生、安全基线、启动保护、Ruff、mypy、后端测试、依赖完整性、Prettier、ESLint、TypeScript、前端测试和 production build。实测指标相同：

| 测量 | 已覆盖 / 总数 | 覆盖率 |
| --- | --- | --- |
| Backend tests | 2607 / 2607 | 全部 PASS |
| Backend statements | 9942 / 10205 | 97.42% |
| Backend branches | 2057 / 2196 | 93.67% |
| Frontend test files / tests | 50 / 579 | 全部 PASS |
| Frontend statements | 2903 / 3015 | 96.28% |
| Frontend branches | 2707 / 2944 | 91.94% |
| Frontend functions | 697 / 702 | 99.28% |
| Frontend lines | 2808 / 2899 | 96.86% |

E2E 从实际测试定义和正式执行结果重新枚举：development 3、integration 18（目录名 integrated）、startup-failure 1，共 22/22。E2E-DEV-001、INT-008、010、014、015、016、017、018 均 PASS。

INT-018 通过真实 UI 创建 Project/结构，进入空正文写作页，输入中文并自动保存，确认真实 ETag、已保存状态和字符数；返回结构再进入后正文恢复，继续修改并立即保存，刷新仍保持完整正文，浏览器审计通过。正式 E2E 清理验证确认占用端口释放、运行时数据不存在。

M5未增加npm依赖；本次M5精简冻结未重复执行DependencyAudit。

保留原有 5 个后端 deprecation warnings，以及 Node 的 NO_COLOR/FORCE_COLOR 提示；未伪造新依赖审计结论。已知 5 个未跟踪开发覆盖率临时文件继续保留，不进入暂存或提交，不绕过删除策略。

## 冻结保护与架构

M0–M4 五个 annotated tags 的 object、target、message、type 均与既有身份一致；15 份冻结文件相对各自 tag 无差异，完整标签身份见 Manifest。未改旧历史、依赖、产品或测试代码。

继续为 Windows local-first、single-user、127.0.0.1、本地 SQLite WAL/FK；Python 3.12.10、FastAPI、SQLAlchemy 2、Alembic；React、TypeScript、Vite、React Router 8.3.0。架构仍为 modular monolith，prefixed ULID、stable object、immutable revisions、head 与 optimistic concurrency。没有云端凭据、telemetry、Git remote 或 push。

## Scope boundary / not implemented

以下均未实现，是本次范围边界，不登记为 M5 已完成能力：

- Markdown、富文本、HTML editor、格式工具栏、正文 preview、第三方 editor framework。
- browser draft recovery、localStorage draft、IndexedDB draft、browser session draft recovery。
- Chapter content history UI、diff、rollback、restore；delete/archive。
- writing status、published status（不等同于已实现的保存状态）。
- AI generation、AI continuation、AI rewrite、AI polish。
- AI Provider、Prompt system、Agent、Skills、Context assembly、retrieval、knowledge base。
- publishing、cloud integration、remote Git。

M6 未开始。本次仅冻结三份文档，静态核验 UTF-8/LF/final newline、严格 JSON、敏感信息和 Git 范围，不在文档后重复完整质量门。

M5 Chapter Writing基础能力验收通过。
