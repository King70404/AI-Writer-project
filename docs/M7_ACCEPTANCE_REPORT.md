# M7 / V1 最终验收报告

## 最终结论与范围

M7 V1完整创作闭环验收通过。

V1 usable foundation = accepted。

本次 DEV-7.2 只验收并冻结既有实现：执行一次 Default、一次 IncludeE2E，随后增加三份冻结文档并进行静态与 Git 检查。没有修改产品、测试、依赖、质量门或既有冻结记录，没有开始 M8。项目定位仍为 Windows 本地、单用户 V1，不是 production SaaS ready、enterprise ready，也不是 publishing platform complete。

## 实现与验收身份

| 项目 | 实测值 |
| --- | --- |
| branch / worktree / staging / remote | main / clean / empty / empty |
| implementation HEAD | `8efd62ccb59b5e2052565311904b04a1a412d0eb` |
| implementation Tree | `d4b0b94581020dfa407cf815479d8ee01cdffa53` |
| implementation commit count | 54 |
| implementation tracked files | 708，由 Git 实测，不含忽略产物 |
| M7 implementation 提交数 | 1 |

M6 标签之后唯一实现提交为 `8efd62ccb59b5e2052565311904b04a1a412d0eb`，主题 `feat(export): add novel text export flow`。

验收提交仅新增本报告、`docs/M7_BASELINE_MANIFEST.json`、`docs/M7_ACCEPTANCE_CHECKLIST.md`，主题固定为 `docs(m7): accept v1 completion`；提交数成为55，tracked files成为711。annotated tag `m7-v1-completion` 的消息为 `M7 V1 completion accepted`，指向该验收提交。最终执行报告记录实际 commit/tree、tag object/target 和三份文档 blob，避免文档自引用哈希。

## M0–M6 冻结保护

下列对象均为 annotated tag（Git type = tag）；消息、对象、目标与原基线一致，21份旧冻结文档相对各自标签 diff 为空。完整消息与身份也记录在 Manifest 中。

| 里程碑 | 标签 | tag object | target commit |
| --- | --- | --- | --- |
| M0 | `m0-engineering-foundation` | `a017a9167aefe09b6ee4026a20dac4cc4ce33780` | `a9a3a6ff361a610aac6ef66a98deed60efccd715` |
| M1 | `m1-project-foundation` | `e7a21496565d57f59e34242770c9cc29131157da` | `15bc7c559cd7021ab409e21bde93a7bf9853e7ce` |
| M2 | `m2-story-bible-foundation` | `3b7a96c5ffcd1a2a4cd3dcd151358616ee1121d3` | `e6262bcf42442012ba5d1a6795ee48649a8b64b7` |
| M3 | `m3-character-foundation` | `a17e18808ece43e7f529c4616f4120d58bb21b57` | `ee78a884ce0d97382f91e4cb1bb7531e80c3f494` |
| M4 | `m4-novel-structure-foundation` | `4a7ff478f0c4e7c2f35213ca1f4c854ffbba7fef` | `082b3d69fc06771809c846a7e7caac6374e738b4` |
| M5 | `m5-chapter-writing-foundation` | `c4f0cdef7f1d84ccac65cb16d969e761381e581a` | `052c6f0e319dff323fdc4865c2a5996cfc1a0143` |
| M6 | `m6-ai-writing-foundation` | `10251f7940ab9ca5d2b728ecfb50bb2c819a9674` | `372ef2e71ddf163b36935cfac79b18589989b1bf` |

## V1 已成立的完整创作闭环

Project → Story Bible → Characters → Outline / Volumes / Chapters → Chapter Writing Workspace → Autosave → Local AI Continue / Rewrite → User explicit accept → Autosave → TXT Export。

- Project：创建、列表、读取、更新、immutable revisions、history list/detail、optimistic concurrency。
- Story Bible：一个 Project 一个 Story Bible；创建、读取、更新、不可变修订、历史列表和详情、ETag / optimistic concurrency。
- Character：Project 内多个 Character；创建、列表、读取、更新、不可变修订、历史列表和详情、ETag / optimistic concurrency。没有 Character relations、World graph、Location / Organization 实体。
- Novel Structure：Outline、Volumes、Chapters；Volume 按 Project 内 position，Chapter 按 Volume 内 position；稳定对象、不可变修订、head、乐观并发。Chapter 始终绑定 Project + Volume。

## Chapter 正文与 Writing Workspace

ChapterRevision 包含 title、summary、position、content。ManuscriptContent 为纯文本，允许空、换行与 TAB，CRLF/CR 规范化为 LF，不 trim，领域长度上限2,000,000字符。结构修改保留正文，正文修改保留结构与归属；结构和正文共享 Chapter revision/head/version，不存在独立正文版本系统。正文更新为带 expected version 的完整替换，事务内生成完整不可变修订并原子更新 head/version。

入口为 `/projects/:projectId/chapters/:chapterId/write`。页面提供纯文本 textarea、字符数、保存状态、立即保存、Ctrl+S、beforeunload 和返回小说结构入口。字符数为 JavaScript UTF-16 code units，不持久化。

Autosave debounce 为1000ms，状态为 saved / dirty / saving / error / conflict；最多一个保存请求在途，保存期间的新输入保留并继续 flush。GET/PUT 返回的真实 ETag 用于 If-Match，不猜测版本。手动保存和 Ctrl+S 复用相同管线。

412 保留本地正文、停止 Autosave，不自动重试、合并或覆盖服务器；可由用户明确丢弃并重新加载。普通错误保留草稿并允许手动重试。beforeunload 保护关闭或刷新时的未保存状态，不宣称已有复杂 SPA 导航阻断或浏览器草稿恢复。

## Local AI Provider 与 Context Assembly

应用接口为 TextGenerationProvider，生产实现为 LocalOpenAICompatibleProvider。仅允许 127.0.0.1、localhost、::1，要求显式端口；localhost 固定到数字 loopback，不使用环境代理，不跟随重定向，禁止 redirect escape。没有云 AI API、API key 或外部 Provider。

配置项为 AIWEBNOVEL_AI_BASE_URL、AIWEBNOVEL_AI_MODEL。OpenAI-compatible 协议请求 POST /chat/completions，stream=false，读取 choices[0].message.content；超时30秒，响应最多1 MiB，生成文本最多50000字符。未配置不阻止应用启动，生成调用返回503；连接/非法响应为502，超时为504。HTTP 错误不泄漏 SQL、traceback、本机路径或上游原始敏感响应。

ChapterWritingContextBuilder 只使用已有公开应用查询服务。总预算60000字符（包括来源标签，不是 token 预算），不发送整本小说全文。确定顺序为 Current Chapter → Outline → Story Bible → Volume → Previous Chapter → Characters → Project：

| 来源 | 限制 |
| --- | --- |
| Current Chapter | 元数据4000；正文最多24000，保留尾部 |
| Outline | 3000 |
| Story Bible | 16000 |
| Volume | 3000 |
| Previous Chapter | 同 Project/Volume 内最近较小 position；元数据3000、正文尾部8000 |
| Characters | 稳定 created_at/id 降序，首页最多100项，只含 name/role，6000字符预算 |
| Project | 3000 |

可选 Outline、Story Bible、Previous Chapter、Characters 缺失不导致失败。Characters 无相关性检索，不加载完整 profile 或历史。预算耗尽时确定性截断/省略；返回 included_sources、omitted_sources、truncated、character_count，不返回完整 prompt。上下文版本或归属改变返回409。

## Continue / Rewrite 与候选安全

ContinueChapter 生成可追加纯文本；RewriteChapterText 仅处理选中文本。可选额外要求最多4000字符，改写选中文本非空、最多50000字符。

AI generation 本身不修改 Chapter，不写 content/head/version，不新增 Revision。候选只在前端 React 内存中保留一份，新生成替换旧候选，刷新即丢失，不自动采用。

生成前必须 flush 到 saved：dirty 立即走既有保存管线；saving 等待并 flush 最新输入；error/conflict 阻止生成，不刷新 ETag 后强行覆盖。一次只允许一个 AI 请求，无队列、无自动重试。

用户明确“追加到正文”或“替换选中文本”后才更新 draft，随后复用既有 Autosave。改写记录 selectionStart、selectionEnd、selectedText；采用时检查原范围文本仍一致，否则拒绝旧候选。丢弃候选不改变正文、不发送保存请求。

## TXT Export

唯一格式为 UTF-8 plain text .txt。ExportProjectManuscript 通过公开 Project / Novel Structure 查询读取当前服务器已保存 head；只导出 Project 标题、Volume 标题、Chapter 标题和 Chapter content。Volume position ASC、Chapter position ASC。

固定逻辑块：

```text
《{project.title}》
第{volume.position}卷 {volume.title}
第{chapter.position}章 {chapter.title}
{chapter.content}
```

块之间两个 LF，整个文件为 UTF-8、LF，并保留 final newline。无 Volume 时只有 Project 标题；空 Volume 保留卷标题；空正文 Chapter 保留章标题。

API 为 `GET /api/v1/projects/{project_id}/export.txt`，Content-Type 为 `text/plain; charset=utf-8`，Content-Disposition 为 `attachment; filename="novel.txt"`，Cache-Control 为 no-store。不存在的 Project 使用既有404错误信封。

后端只在内存组装，不写服务器文件，不改变业务状态；真实迁移 SQLite 测试比较重复导出前后的完整 iterdump，结果完全相同，文件集合不变。导出不含摘要、设定、人物资料、历史修订、AI 候选或未保存浏览器草稿。

前端入口为 Project 详情“导出小说”，复用共享 getText，创建 Blob / object URL / download anchor，finally 移除 anchor 并 revoke object URL。文件名替换 Windows 非法及控制字符、trim，空名回退 novel.txt；exporting 时禁止重复点击，失败可明确重试；不新增路由。

## 最终库存与数据库

当前真实 OpenAPI 重新枚举37个 method/path，Manifest 完整记录。旧36条全部保留，M7 仅新增 TXT Export GET，无第38条意外 API。局部库存仍为 Project-owned 6、Novel Structure 11、Chapter Content 2、AI 2。

前端路由12条，Manifest 完整枚举，M7 无新增 route：

- `/`
- `/projects`
- `/projects/:projectId`
- `/projects/:projectId/history`
- `/projects/:projectId/story-bible`
- `/projects/:projectId/story-bible/history`
- `/projects/:projectId/characters`
- `/projects/:projectId/characters/:characterId`
- `/projects/:projectId/characters/:characterId/history`
- `/projects/:projectId/structure`
- `/projects/:projectId/chapters/:chapterId/write`
- `*`

Metadata 为18张表：Project、Story Bible、Character、Outline、Volume、Chapter 各自 stable/revisions/heads 三表。Alembic head 为 `0006_add_chapter_manuscript_content`，12个 Revision 不可变 update/delete 触发器；Manifest 枚举全部表和触发器。无0007，无 AI / Prompt / Export / Draft 表。正式迁移测试在隔离 SQLite 中验证真实库存，不访问正式创作数据库。

| Migration | blob ID |
| --- | --- |
| 0001_initialize_database | `63112b9b7d4510decb9b38de07ceb867491f2e05` |
| 0002_create_project_foundation | `5aa10200b7290278000cc21951850960dc914089` |
| 0003_create_story_bible_foundation | `deb9c9c05fa2af8dd78c701c1afe72fb26b7fc99` |
| 0004_create_character_foundation | `175044bfad61a4595000e4ec3dc01c5db6b3e641` |
| 0005_create_novel_structure_foundation | `2982c22e8406d74b9a913f2b468137484c7490dc` |
| 0006_add_chapter_manuscript_content | `c230b40dbe955ccacbbf246f3596d1ee5cdb63c8` |

## 正式质量门证据

两门均在三份文档创建前按顺序各执行一次，未重跑：

| 正式命令 | 结果 | real exit |
| --- | --- | --- |
| `.\scripts\quality_gate.ps1` | PASS | 0 |
| `.\scripts\quality_gate.ps1 -IncludeE2E` | PASS；E2E 24/24 | 0 |

两门后端均2766/2766，前端均54 files、660/660，无失败或跳过。覆盖率分子/分母一致：

| 指标 | covered / total | 百分比 |
| --- | --- | --- |
| Backend statements | 10310 / 10573 | 97.51% |
| Backend branches | 2107 / 2246 | 93.81% |
| Frontend statements | 3048 / 3160 | 96.45% |
| Frontend branches | 2835 / 3071 | 92.31% |
| Frontend functions | 730 / 735 | 99.31% |
| Frontend lines | 2942 / 3033 | 96.99% |

后端分母来自正式 coverage.py TOTAL（语句 missed=263），独立覆盖率检查器输出97.51% / 93.81%。10310为总语句减 missed；2107为该分支分母与两位百分比对应的唯一整数 covered count，未把语句和分支的混合 Cover 百分比误作语句覆盖率。

Ruff format、Ruff、mypy、Prettier、ESLint、TypeScript、生产构建、仓库卫生、安全与启动安全检查、Python/npm 依赖完整性检查通过。保留5条既有后端弃用警告及 Node 颜色环境警告，不伪装为零警告。

E2E 真实分类为 development 3、integrated 20、startup-failure 1，总计24/24；全部 ID 和来源在 Manifest 中。关键 DEV-001、INT-008、INT-010、INT-014～020 全部通过。INT-017 验证小说结构；INT-018 验证正文与 Autosave；INT-019 验证真实 production provider 对受控 loopback 协议服务的调用，以及明确采用后保存和刷新保留，不能据此宣称某个真实模型的文学质量。

INT-020 使用真实浏览器 download 事件，取得真实下载文件并以 UTF-8 读取；逐项验证 Project/Volume/Chapter 标题、已保存正文、完整内容和顺序、LF、文件名及浏览器审计。不是只检查 HTTP 200。测试删除下载文件，质量门清理检查确认归属端口释放、E2E runtime 和成功产物不存在。

M7未新增第三方依赖；本次精简冻结未重复运行DependencyAudit。backend/pyproject.toml、frontend/package.json、frontend/package-lock.json 相对 M6 不变，不声称新的漏洞审计结果。

文档创建后仅执行 UTF-8/LF/final newline、严格 JSON、敏感信息和绝对路径扫描、Git diff --check 与范围/冻结检查；不再运行 Default 或 IncludeE2E。

## 架构、安全与使用边界

Windows 11 / local-first / single-user；后端 FastAPI、Python 3.12.10，绑定127.0.0.1；前端 React、TypeScript、Vite、React Router 8.3.0；本次运行 Node24.18.0、npm11.16.0。数据库 SQLite WAL/FK、SQLAlchemy 2、Alembic；modular monolith、typed prefixed ULIDs、稳定对象 + immutable revisions + head + optimistic concurrency。

无云 AI API、API credentials、应用 telemetry、remote Git 或 push。本地 AI loopback-only、redirect escape blocked；错误不泄漏 SQL、traceback、本机路径、上游原始敏感响应。测试使用隔离数据，未访问正式创作数据。

本地模型服务需用户另行配置；本 V1 不负责模型安装、启动或质量保证。导出基于服务器已保存内容；Autosave 不是浏览器草稿恢复。上述限制不改变已验收的基础创作闭环。

## Not implemented / Future scope

以下均为明确未实现的未来范围，不是 V1 验收缺陷，不得登记为已有能力：

- DOCX
- EPUB
- PDF
- Markdown export
- publishing platform
- cloud sync
- browser draft recovery
- localStorage / IndexedDB drafts
- Markdown editor
- rich text editor
- Chapter content history UI
- diff
- rollback
- delete/archive/restore
- World entities
- Locations
- Organizations
- Character relations
- Agent
- Skills
- Tool calling
- Prompt management
- AI Chat
- Streaming
- SSE
- WebSocket
- model manager
- model downloader
- model launcher
- cloud AI provider
- API key management
- embeddings
- vector database
- RAG platform
- knowledge graph
- timeline
- advanced consistency checker
- AI candidate history
- AI generation history persistence

## 封板边界

V1 usable foundation = accepted。M8 not started。此任务以三份文档的验收提交和 annotated tag 为终点，不扩展功能。
