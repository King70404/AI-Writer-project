# M5 Chapter Writing Foundation 验收清单

DEV-5.3：仅冻结已完成的 DEV-5.1/DEV-5.2；详细身份与完整库存以 `docs/M5_BASELINE_MANIFEST.json` 为准，验收说明见 `docs/M5_ACCEPTANCE_REPORT.md`。

## Implemented / verified

- [x] main；实现 HEAD `0de5193bc6100d1b6d934e8a2aaccdb296e6d52c`，Tree `65cb5463f82b8cee1c2653eba7ca32c3896fd00b`，49 个提交、670 个 tracked files。
- [x] M4 后只有 `da382ecadfb706cf860eb4c67e5a3bfc397b6e74`、`0de5193bc6100d1b6d934e8a2aaccdb296e6d52c` 两个实现提交；工作树干净、暂存为空、remote 为空。
- [x] M0–M4 标签 object/target/message/type 不变；15 份冻结文档与各自 tag 无差异。
- [x] ChapterRevision 具有 title/summary/position/content；正文为严格纯文本，允许空、Tab、LF，CRLF/CR 转 LF，最大 2,000,000 字符，不 trim，拒绝非法控制字符。
- [x] CreateChapter 仍只接收结构字段，Revision 1 content 为空。
- [x] 结构更新保留正文；正文完整替换保留结构及 Project/Volume 归属。
- [x] 共用 stable object、revision、head、revision_number、concurrency_version，每次修改创建完整不可变版本。
- [x] GetChapterContent / UpdateChapterContent 经应用服务和事务 Repository 执行；expected_version 防止 stale，无自动 retry/merge。
- [x] Metadata 18 张业务表；仅 chapter_revisions 新增 content TEXT NOT NULL，stable chapters 无 content/body/draft/word_count。
- [x] Alembic 0006，无 0007；0001–0006 migration blobs 与规定一致。
- [x] 0005 → 0006 → 0005 → 0006 兼容性通过；旧 ChapterRevision 正文为空、结构保持不变。
- [x] 12 个不可变 trigger 保持不变，ChapterRevision no UPDATE/no DELETE 保护 content；SQLite WAL/FK 启用。
- [x] 真实 production OpenAPI 34 条；M4 原 32 条保留，仅新增 Chapter content GET/PUT。
- [x] GET 返回正文当前 snapshot 和 strong ETag；PUT body 仅 content，并发送真实 If-Match，成功更新服务端 ETag。
- [x] 缺失/错误/stale If-Match 为 428/400/412，不存在为 404；错误不泄漏内部信息或正文。
- [x] 原 session/CSRF、Host/Origin、JSON 与默认 1 MiB 请求体保护保持；领域字符上限不等于 HTTP 字节上限。
- [x] 12 条前端路由；唯一新增 `/projects/:projectId/chapters/:chapterId/write`。
- [x] Structure Workspace 有「写正文」入口；先加载并检查归属，再显示章节信息、纯文本 textarea、保存状态、字符数、立即保存和返回结构。
- [x] Autosave 1000ms，状态 saved/dirty/saving/error/conflict。
- [x] inFlight guard 串行保存；保存期间新输入保持 dirty 并安排下一次保存，不错误显示已保存。
- [x] 412 停止自动保存、保留本地正文，不强制覆盖；仅显式选择丢弃本地正文并重新加载。
- [x] 普通失败保留正文，允许编辑及手动重试，没有无限自动重试。
- [x] 立即保存和编辑区 Ctrl+S 复用同一 pipeline；Ctrl+S preventDefault。
- [x] beforeunload 只在未保存风险状态保护关闭/刷新；saved 不提示；没有复杂 SPA 路由阻断。
- [x] 字符数为 content.length，JavaScript UTF-16 code units，不持久化；没有 word_count/character_count 数据字段。
- [x] Default 正式门仅一次 PASS，真实 exit 0，创建冻结文档之前执行。
- [x] IncludeE2E 正式门仅一次 PASS，真实 exit 0，Default 通过后且创建冻结文档之前执行。
- [x] 两门 Backend 均 2607/2607；statements 9942/10205（97.42%），branches 2057/2196（93.67%）。
- [x] 两门 Frontend 均 50 files / 579 tests；statements 2903/3015（96.28%），branches 2707/2944（91.94%），functions 697/702（99.28%），lines 2808/2899（96.86%）。
- [x] E2E 22/22：development 3、integration 18、startup-failure 1；所有场景在 Manifest 枚举。
- [x] DEV-001、INT-008/010/014/015/016/017/018 全部通过；INT-018 覆盖空正文、中文自动保存、真实 ETag、字符数、重新进入、立即保存、刷新恢复与浏览器审计。
- [x] 正式构建、静态规则、类型检查、依赖完整性通过；E2E 端口释放、运行时数据无残留。
- [x] M5未增加npm依赖；本次M5精简冻结未重复执行DependencyAudit。
- [x] 已知 5 个未跟踪开发覆盖率临时文件不暂存、不提交；不绕过删除策略。
- [x] Windows local-first/single-user/127.0.0.1；Python 3.12.10/FastAPI/SQLAlchemy 2/Alembic；React/TypeScript/Vite/React Router 8.3.0；modular monolith、prefixed ULID、不可变版本与乐观并发。
- [x] 不读取正式创作数据，没有云凭据、telemetry、Git remote 或 push。

## Scope boundary / not implemented

以下未实现；不是待补齐的 M5 验收缺陷，也不勾选为用户能力：

- Markdown、富文本、HTML editor、格式工具栏、正文 preview、第三方 editor framework。
- browser draft recovery、localStorage draft、IndexedDB draft、browser session draft recovery。
- Chapter content history UI、diff、rollback、restore、delete/archive。
- writing status、published status。
- AI generation、AI continuation、AI rewrite、AI polish。
- AI Provider、Prompt system、Agent、Skills、Context assembly、retrieval、knowledge base。
- publishing、cloud integration、remote Git。

## 冻结操作合同

只增加三份 M5 文档，进行 UTF-8/LF/final newline、严格 JSON、无秘密及无本机绝对路径、Git diff --check 和暂存范围静态检查。文档后不再运行 Default/IncludeE2E。

验收提交主题固定 `docs(m5): accept chapter writing foundation`，提交数 50、tracked files 673。annotated tag `m5-chapter-writing-foundation` 的消息固定 `M5 chapter writing foundation accepted`，指向验收提交。最终 Git/tag/blob 与 M0–M4 保护复核结果记录于执行报告。

M6 未开始，不创建 M6 文档、标签或 AI 功能。
