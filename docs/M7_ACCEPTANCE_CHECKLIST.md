# M7 / V1 验收清单

## 结论

M7 V1完整创作闭环验收通过。

V1 usable foundation = accepted。该 Windows 本地单用户 V1 已具备日常完成网文基础创作流程的能力；本地 AI 需另行配置兼容模型服务，模型文学质量不属于本次测试保证。不宣称 SaaS、企业级或完整发布平台就绪。

## Implemented / Accepted

- [x] DEV-7.2 仅正式验收与冻结；实现 HEAD 为 `8efd62ccb59b5e2052565311904b04a1a412d0eb`，Tree 为 `d4b0b94581020dfa407cf815479d8ee01cdffa53`，count=54，tracked files=708。
- [x] M7 实现链精确一个提交：`feat(export): add novel text export flow`。
- [x] 执行前 main、工作区干净、暂存区空、无 remote；M7 文档与标签不存在。
- [x] M0–M6 七个 annotated tag 的对象、目标、类型、消息保持不变；21份冻结文件相对各自标签 diff 为空。
- [x] 主链：Project → Story Bible → Characters → Outline / Volumes / Chapters → Chapter Writing Workspace → Autosave → Local AI Continue / Rewrite → User explicit accept → Autosave → TXT Export。
- [x] Project 创建/列表/读取/更新、不可变修订、历史列表/详情、乐观并发。
- [x] 每 Project 一个 Story Bible，创建/读取/更新、不可变历史、ETag 并发。
- [x] 每 Project 多个 Character，创建/列表/读取/更新、不可变历史、ETag 并发；不含关系图或 World 实体。
- [x] Outline / Volume / Chapter 稳定对象、修订与 head；卷在 Project 内、章在 Volume 内按 position；Chapter 绑定 Project + Volume。
- [x] ChapterRevision 为 title/summary/position/content；纯文本 content 可空、CRLF/CR→LF、不 trim，领域上限2,000,000字符。
- [x] 结构更新保留正文，正文更新保留结构；共享 Chapter revision/head/version。
- [x] 写作入口 `/projects/:projectId/chapters/:chapterId/write`，textarea、字符数、1000ms Autosave、立即保存、Ctrl+S、beforeunload。
- [x] saved/dirty/saving/error/conflict 状态、单一在途保存、晚到输入继续 flush；真实 ETag / If-Match。
- [x] 412 保留本地正文、停止 Autosave，不自动覆盖、重试或合并。
- [x] TextGenerationProvider / LocalOpenAICompatibleProvider，只允许127.0.0.1、localhost、::1；无云 Provider/API key、无重定向逃逸。
- [x] Context 总预算60000字符；可组装 Project、Story Bible、Outline、Volume、Current/Previous Chapter、Characters；当前正文尾部24000、前章正文尾部8000、Characters 稳定顺序6000预算，无相关性检索，可选来源缺失可用。
- [x] ContinueChapter / RewriteChapterText 生成本身不写 Chapter、Revision、head 或 version。
- [x] 候选只在前端内存，不自动采用；明确追加/替换后进入 draft，再走既有 Autosave。
- [x] Save-before-generate：dirty 保存、saving 等待并 flush、error/conflict 阻止生成。
- [x] Rewrite 保存 selectionStart/selectionEnd/selectedText，采用时原范围变化则拒绝旧候选。
- [x] TXT Export 只含当前已保存 Project/Volume/Chapter 标题和正文，卷/章 position ASC。
- [x] UTF-8、LF、逻辑块两个 LF、final newline；无卷/空卷/空章可导出且保留相应标题。
- [x] 后端内存组装、无服务器文件、无业务状态写入；真实 SQLite 全量 iterdump 前后相同。
- [x] GET `/api/v1/projects/{project_id}/export.txt`；text/plain; charset=utf-8；attachment; filename="novel.txt"。
- [x] 前端 Blob/object URL/download anchor，清理 anchor/revoke URL，最小 Windows 文件名清洗，禁止重复下载点击。
- [x] Production API37，旧36完整保留，仅新增 Export GET，无第38条；局部 Project-owned6、Novel Structure11、Chapter Content2、AI2。
- [x] 前端12路由且 M7 未增路由；Manifest 完整枚举37 method/path 和12 route。
- [x] Metadata18，Alembic `0006_add_chapter_manuscript_content`，Revision immutable triggers12；迁移0001–0006 blob不变，无0007，无 AI/Prompt/Export/Draft 表。
- [x] Default 正式门一次 PASS，real exit=0。
- [x] IncludeE2E 正式门一次 PASS，real exit=0；没有重跑。
- [x] 两门 Backend2766/2766；statements10310/10573=97.51%，branches2107/2246=93.81%。
- [x] 两门 Frontend54 files、660/660；statements3048/3160=96.45%，branches2835/3071=92.31%，functions730/735=99.31%，lines2942/3033=96.99%。
- [x] E2E24/24：development3、integrated20、startup-failure1；DEV-001、INT-008、INT-010、INT-014～020 均通过。
- [x] INT-020 真实 download 事件、真实文件及内容读取，验证标题/已保存正文/顺序，不是仅 HTTP200。
- [x] 静态、安全、依赖完整性、生产构建通过；E2E 归属端口释放、runtime 与成功产物清理通过。
- [x] M7未新增第三方依赖；本次精简冻结未重复运行DependencyAudit，不声称新的审计结果。
- [x] Windows local-first/single-user、FastAPI/Python3.12.10、React/TypeScript/Vite/Router8.3.0、SQLite WAL/FK/SQLAlchemy2/Alembic、127.0.0.1、modular monolith、prefixed ULIDs、不可变修订和乐观并发。
- [x] 无云 AI API、API credentials、telemetry、Git remote/push；HTTP 错误不泄漏 SQL/traceback/本机路径/上游敏感响应。
- [x] 只新增三份 M7 docs，严格 JSON、UTF-8、LF、final newline、无真实敏感信息或绝对本机路径；文档后仅静态与 Git 复核，不再运行完整门。

## 最终封板契约

验收提交仅包含 `docs/M7_ACCEPTANCE_REPORT.md`、`docs/M7_BASELINE_MANIFEST.json`、`docs/M7_ACCEPTANCE_CHECKLIST.md`。主题 `docs(m7): accept v1 completion`，count=55，tracked files=711。annotated tag `m7-v1-completion`，message=`M7 V1 completion accepted`，target=本验收提交。

实际 acceptance commit/tree、tag object/target/type/message、三个文档 blob 和最终 tag diff / M0–M6 / Git 复核结果记录在执行报告，避免文档哈希自引用。最终 main、工作区干净、暂存区空、remote 空。M8 not started。

## Not implemented / Future scope

以下全部未实现，属于未来范围，不是 V1 验收缺陷：

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

## 已知边界

- 本地模型服务需独立配置，协议 E2E 不等于模型文学质量保证。
- 未保存草稿、未采用 AI 候选不会被导出；beforeunload 不等于浏览器草稿恢复或复杂 SPA 导航阻断。
- 5条既有后端弃用警告与 Node 颜色环境警告仍存在；两种正式门均通过，未为消除警告改变依赖。
- M8 未开始；V1 封板后不在本任务中扩功能。
