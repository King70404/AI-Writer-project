# M6 AI Writing Foundation 验收报告

## 范围与实现基线

DEV-6.3 只正式验收并冻结 DEV-6.1 与 DEV-6.2，不新增功能，不开始 M7。完整产品链为：

Chapter Writing Workspace → 保存当前正文 → Context Assembly → Local AI Provider → Candidate → 用户明确采用 → 既有 Autosave → ChapterRevision。

| 实现身份 | 值 |
| --- | --- |
| implementation HEAD | `8036abe94f0ef430d7ec0874f2951d2c8770b79f` |
| implementation Tree | `dec6965d02cd6354c41d4d1b6880f26df6c97f08` |
| implementation commit count | 52 |
| implementation tracked files | 695（由 Git 实测，不含忽略的产物） |
| branch / worktree / staging / remote | main / clean / empty / empty |

M5 冻结后精确只有两个实现提交：

1. `322a9cb811dfa7065cd9d536010e498a284cf21c` — `feat(ai-writing): add local generation backend`。
2. `8036abe94f0ef430d7ec0874f2951d2c8770b79f` — `feat(frontend): add ai writing assistance`。

验收提交只增加本报告、`docs/M6_BASELINE_MANIFEST.json`、`docs/M6_ACCEPTANCE_CHECKLIST.md`；提交数成为53，tracked files成为698。主题固定为 `docs(m6): accept ai writing foundation`。annotated tag `m6-ai-writing-foundation` 的消息为 `M6 ai writing foundation accepted`，指向承载三份文档的验收提交。实际验收 commit/tree、tag object/target 与文档 blob 在最终执行报告记录，避免自引用哈希。

## Provider 架构与 local-only 安全

接口为 `TextGenerationProvider`，生产实现为 `LocalOpenAICompatibleProvider`，使用 Python 标准库 HTTP 客户端。配置名称为 `AIWEBNOVEL_AI_BASE_URL`、`AIWEBNOVEL_AI_MODEL`；无 API key、无云 credential。应用不安装、下载或启动本地模型。

仅允许 loopback：`127.0.0.1`、`localhost`、`::1`，必须提供显式非零端口。拒绝公网和局域网 IP、外部域名、URL userinfo、query、fragment；localhost 固定解析至数字 loopback，不依赖 DNS。客户端不使用环境代理，不跟随 redirect，不能借重定向向非本机发送正文。

正式协议为在配置 base path 后请求 `POST /chat/completions`，body 包含 model、messages、stream=false，读取 `choices[0].message.content`。超时30秒，响应最多1 MiB，生成文本最多50000字符，规范化正文换行并验证内容与模型名称。无 streaming、tool calling、function calling 或 JSON mode。

Provider 未配置不影响应用启动；调用生成接口时返回503。未配置/配置无效为503，连接失败/非法上游响应为502，超时为504；输入错误为422，不存在的 Chapter 为404，读取上下文期间版本或归属变化为409。安全错误不拼接上游 body、traceback、本机路径、SQL 或 Provider URL。

## Context Builder 与确定性预算

`ChapterWritingContextBuilder` 仅依赖已有模块的公开应用查询服务，不直接访问 ORM/Repository。总字符预算为60000，包含来源标签，使用确定的顺序与字符截断，不是 token 预算，也不是完整小说全文发送。

实际组装顺序及上限：

| 来源 | 局部预算与行为 |
| --- | --- |
| 当前 Chapter 元数据 | 4000；id、Project/Volume归属、title、summary、position |
| 当前 Chapter content | 24000，超长保留尾部 |
| Outline（可选） | 3000 |
| Story Bible（可选） | 16000 |
| 当前 Volume | 3000 |
| Previous Chapter 元数据 | 3000 |
| Previous Chapter content（可选） | 8000，超长保留尾部 |
| Characters（可选） | 6000 |
| Project基础信息 | 3000 |

所有来源还受60000全局剩余预算约束，后续来源可能缩短或省略。当前 Chapter 的元数据和正文须具有一致 revision 与归属；Previous Chapter 也检查对应 revision。

Previous Chapter 只选同一 Volume、同一 Project 内 position 最近且小于当前章的一个 Chapter，不做全书搜索。Characters 使用当前 Project 列表首100项的 name/role，按既有 created_at/id 降序稳定排列，不加载 profile/history；有后续页时标记 truncated。没有 Chapter-character 关系或角色相关性检索。

Outline、Story Bible、Previous Chapter、Characters 缺失是可选来源缺失，不导致生成失败；持久化错误不伪装为可选缺失。Context manifest 显式返回 included_sources、omitted_sources、truncated、character_count；HTTP不返回完整 Prompt、system prompt 或 Provider URL。

## Continue、Rewrite 与候选边界

正式应用服务为 `AIWritingService.continue_chapter` 和 `AIWritingService.rewrite_chapter_text`。

- ContinueChapter：规范 Chapter ID + 可选 instruction；instruction最大4000字符，允许空，换行规范化后trim。指令要求保持语言、人称、风格与设定，避免大段重复，返回可追加的纯文本候选。
- RewriteChapterText：Chapter ID + 指定text + 可选instruction；text非空、支持多段、最大50000字符。只改写指定文本，默认保持原意，不续写后续情节。
- GenerationCandidate包含operation、text、model、context；仅为 ephemeral proposal。生成调用本身不修改content、head、concurrency_version或revision count，不持久化生成记录。
- Prompt中的“保持风格/设定”等是生成目标，不是对任意模型文学质量的确定性保证。

真实 production OpenAPI 已重新枚举为36个method/path，M5的34条全部保留，M6恰好新增：

- `POST /api/v1/chapters/{chapter_id}/ai/continue`
- `POST /api/v1/chapters/{chapter_id}/ai/rewrite`

全部36条在 Manifest 中逐项列出。沿用现有本地安全session/CSRF、Host/Origin和JSON请求保护，候选响应为 no-store。

## Chapter Writing Workspace 与 Autosave

没有新增页面路由，12条既有路由在 Manifest 中完整枚举。现有写作页内增加轻量“AI写作助手”，含共用“额外要求（可选）”、续写、改写选中文本、只读AI候选、追加/替换和丢弃，不是聊天界面；正文仍为textarea。

生成状态为idle/generating/success/error，同一时间最多一个AI请求，Continue与Rewrite串行，无请求队列。生成期间允许继续编辑。

Save-before-generate使用 `useChapterWriting.flush`，复用同一保存管线：

- saved直接生成；dirty立即保存；saving等待当前请求。
- 保存期间继续输入则继续flush最新正文，直到当前正文真正saved。
- error/conflict阻止生成并提示先保存，不自动刷新ETag或覆盖服务器。

Continue与Rewrite成功都不自动修改textarea。只保留一个当前候选，新生成替换旧候选，候选仅在React内存，刷新即消失。

显式采用Continue：空正文直接candidate；以换行结尾则current + candidate；否则current + "\n\n" + candidate。操作只使draft变为dirty。

Rewrite要求选中非空正文，并在生成时记录selectionStart、selectionEnd、selectedText。采用前检查 `currentContent.slice(start,end) === originalSelectedText`；若变化，拒绝旧候选并提示重新选择、生成。有效时使用 `content[0:start] + candidate + content[end:]` 替换，draft变为dirty。不能依赖AI返回时的浏览器当前光标位置。

丢弃只清空候选，正文不变，不发送正文保存请求。采用后的持久化继续由M5的1000ms Autosave、立即保存、Ctrl+S、同一If-Match/ETag完成，无第二套正文PUT。412继续保留本地正文并阻止自动覆盖。

503提示本地AI未配置/配置无效；502提示连接失败或响应无效；504提示超时。AI错误保留正文、ETag、Autosave状态与instruction，可手动重试，无无限自动retry。save-before-generate可因保存dirty正文推进版本，但AI生成结果本身不推进Chapter版本。

## 数据库、迁移与冻结保护

M6数据库变化为0：正式Metadata18表，Alembic head为 `0006_add_chapter_manuscript_content`，无0007。无generation、prompt、provider或AI history表。SQLite WAL/FK及12个revision不可变触发器保持不变，表和触发器名称完整见Manifest。

| Migration | Git blob |
| --- | --- |
| 0001 | `63112b9b7d4510decb9b38de07ceb867491f2e05` |
| 0002 | `5aa10200b7290278000cc21951850960dc914089` |
| 0003 | `deb9c9c05fa2af8dd78c701c1afe72fb26b7fc99` |
| 0004 | `175044bfad61a4595000e4ec3dc01c5db6b3e641` |
| 0005 | `2982c22e8406d74b9a913f2b468137484c7490dc` |
| 0006 | `c230b40dbe955ccacbbf246f3596d1ee5cdb63c8` |

六份迁移工作树blob与冻结身份一致。完整后端迁移套件在独立SQLite数据库验证实际表与12个触发器，包括0006迁移周期兼容性；本次也独立枚举Metadata和Alembic head，未访问正式创作数据。

M0–M5六个annotated tag的object、target、message、type均保持原身份；18份冻结文档相对各自tag无差异，完整身份见Manifest。M5 object为 `c4f0cdef7f1d84ccac65cb16d969e761381e581a`，target为 `052c6f0e319dff323fdc4865c2a5996cfc1a0143`，消息为 `M5 chapter writing foundation accepted`。

## 本次正式质量门与证据

两种正式门在上述implementation HEAD、创建任何M6文档之前，各执行一次。Default成功后才运行IncludeE2E。未重跑，文档后不重复完整门。

| 命令 | 次数 | 结果 | 真实退出码 |
| --- | --- | --- | --- |
| `.\scripts\quality_gate.ps1` | 1 | PASS | 0 |
| `.\scripts\quality_gate.ps1 -IncludeE2E` | 1 | PASS，E2E 23/23 | 0 |

两门均通过仓库卫生、安全与启动保护、Ruff、mypy、后端测试、依赖完整性、Prettier、ESLint、TypeScript、前端测试和production build；指标相同：

| 指标 | 分子 / 分母 | 覆盖率 |
| --- | --- | --- |
| Backend tests | 2755 / 2755 | PASS |
| Backend statements | 10260 / 10523 | 97.50% |
| Backend branches | 2101 / 2240 | 93.79% |
| Frontend files / tests | 52 / 634 | PASS |
| Frontend statements | 3009 / 3121 | 96.41% |
| Frontend branches | 2812 / 3049 | 92.22% |
| Frontend functions | 721 / 726 | 99.31% |
| Frontend lines | 2904 / 2995 | 96.96% |

Default后端测试用时363.44秒，IncludeE2E后端测试用时359.39秒。原有5个后端deprecation warnings与Node颜色环境提示不影响退出码；本任务没有为消除提示改变依赖。

E2E重新枚举并全部执行：development 3，integration 19（实际目录integrated），startup-failure 1，共23/23，所有ID见Manifest。DEV-001、INT-008、010、014～019全部PASS。

INT-019 `AI writing assistance flow` 用时7.2秒，真实走production backend → LocalOpenAICompatibleProvider → 受控loopback OpenAI-compatible测试server，不是frontend mock。它创建独立Project/结构，输入中文并真实Autosave；Continue候选返回时正文不变，明确追加后保存、刷新恢复；真实textarea选择范围改写，候选返回时正文仍不变，明确替换后保存、刷新恢复。浏览器console/API审计通过，E2E清理确认所有受控端口释放、runtime数据不存在。

M6相对M5未修改 `backend/pyproject.toml`、`frontend/package.json`、`frontend/package-lock.json`，未增加第三方依赖；本次不执行IncludeDependencyAudit，不声称取得新的漏洞审计结果。

## Runtime、限制与未实现范围

Windows 11 local-first、single-user、backend绑定127.0.0.1；Python3.12.10、Node24.18.0、npm11.16.0；FastAPI/SQLAlchemy2/Alembic/SQLite与React/TypeScript/Vite/React Router8.3.0。架构继续为模块化单体、带类型前缀ULID、稳定对象/不可变版本/head与乐观并发。

实际使用需另行配置本机AI服务；受控E2E证明协议链路与采用安全，不证明某模型的文学质量或本机已配置可用模型。M6没有更改M5的浏览器草稿恢复策略，没有第二套写入机制。

以下均是 scope boundary / not implemented，不是本次验收缺陷，不登记为已实现能力：

- Streaming。
- SSE。
- WebSocket。
- AI Chat。
- conversation history。
- Prompt CRUD。
- Prompt管理页面。
- Prompt数据库。
- Agent。
- Skills。
- Tool calling。
- function calling。
- JSON mode。
- 模型选择器。
- 模型下载器。
- 模型启动器。
- 云Provider。
- API key管理。
- Vector DB。
- Embeddings。
- RAG平台。
- 知识图谱。
- 长期记忆。
- AI候选历史。
- AI生成记录持久化。
- 自动采用AI结果。
- AI自动写回正文。
- Markdown。
- 富文本。

M7未开始；没有Export、发布流程、M7文档或标签。本次仅新增三份冻结文档，执行UTF-8/LF/final newline、严格JSON、敏感信息和绝对路径扫描、Git diff与暂存范围检查；不改变产品或测试代码。

M6 AI Writing基础能力验收通过。
