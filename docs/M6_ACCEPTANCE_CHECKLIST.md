# M6 AI Writing Foundation 验收清单

DEV-6.3：只冻结已完成的DEV-6.1/DEV-6.2。完整机器可读库存见 `docs/M6_BASELINE_MANIFEST.json`，事实与证据说明见 `docs/M6_ACCEPTANCE_REPORT.md`。

## Implemented / verified

- [x] main；implementation HEAD `8036abe94f0ef430d7ec0874f2951d2c8770b79f`、Tree `dec6965d02cd6354c41d4d1b6880f26df6c97f08`；52个提交、695个Git跟踪文件；执行前工作区干净、暂存与remote为空。
- [x] M5后实现链精确为 `322a9cb811dfa7065cd9d536010e498a284cf21c` 和 `8036abe94f0ef430d7ec0874f2951d2c8770b79f` 两个提交。
- [x] M6文档与tag执行前均不存在；M0–M5标签object/target/message/type不变；18份旧冻结文档diff为空。
- [x] Provider接口TextGenerationProvider，生产LocalOpenAICompatibleProvider；配置AIWEBNOVEL_AI_BASE_URL/AIWEBNOVEL_AI_MODEL，无API key或云credential。
- [x] 仅loopback 127.0.0.1/localhost/::1，显式端口；拒绝公网、LAN、外部域名与URL userinfo，不跟随redirect，不使用环境代理。
- [x] 未配置Provider不阻止应用启动，生成时503；连接/非法响应502；超时504；不泄漏原始body、traceback、路径。
- [x] 协议POST /chat/completions，model/messages/stream=false，读取choices[0].message.content；30秒超时、响应最多1 MiB。
- [x] Context Builder只依赖公开应用查询；60000字符总预算含来源标签，固定来源顺序、固定局部预算及确定性截断。
- [x] 上下文来源包含Project、可选Story Bible/Outline、当前Volume/Chapter、可选Previous Chapter/Characters；可选缺失不失败。
- [x] 当前Chapter含id/title/summary/position/content及归属，正文超长保留尾部24000字符；校验revision与归属一致。
- [x] Previous Chapter只选同Volume内最近较小position，正文保留尾部8000字符，不做全书搜索。
- [x] Characters按Project列表created_at/id降序，首100项name/role，总预算6000字符；有后续页标记truncated，不做相关性检索或profile/history加载。
- [x] Context manifest含included_sources/omitted_sources/truncated/character_count；HTTP不返回完整Prompt、system prompt或Provider URL。
- [x] ContinueChapter接收chapter_id及可选instruction，最大4000字符、允许空、trim，返回可追加纯文本候选。
- [x] RewriteChapterText只改写指定非空多段text，最多50000字符，默认保留原意；instruction同Continue规则。
- [x] 生成候选不修改Chapter content/head/concurrency_version/revision count；无候选持久化。
- [x] 真实OpenAPI重新枚举36条，M6 AI恰好2条continue/rewrite POST；全部method/path见Manifest。
- [x] Metadata18表、Alembic0006、无0007；0001–0006 blobs不变；12个revision不可变触发器保持；无AI表。
- [x] 前端精确12条路由，Manifest完整枚举；M6没有新增页面路由。
- [x] 既有Chapter Writing Workspace保持textarea；加入额外要求、续写、选中改写、只读候选、明确采用和丢弃。
- [x] 生成前saved直接调用；dirty立即保存；saving等待；保存中有新输入继续flush直到当前正文saved。
- [x] save error/conflict阻止生成；不自动刷新ETag或强制覆盖；提示先保存当前正文。
- [x] AI状态idle/generating/success/error；同时最多一个生成请求，Continue/Rewrite不可并发，无队列。
- [x] Continue及Rewrite成功都不自动改变正文；生成期间允许继续编辑；只有用户明确采用才改draft。
- [x] Continue采用规则为：空正文直接候选；换行结尾直接拼接；否则增加两个LF再拼接。
- [x] Rewrite保存start/end/selectedText快照；采用前检查原slice相等，不相等拒绝并要求重新生成。
- [x] Rewrite采用只替换原范围；采用后dirty，由原1000ms Autosave保存，无第二套PUT。
- [x] 丢弃清空候选、正文不变、无保存请求；仅保留一个当前候选，新生成替换旧候选，刷新消失。
- [x] AI 503/502/504提示安全明确；失败保留正文/ETag/Autosave状态/instruction，可手动重试，无无限自动retry。
- [x] 立即保存、Ctrl+S、If-Match、ETag继续复用M5保存管线；412保护保持。
- [x] Default在创建文档前仅一次PASS、真实exit0；IncludeE2E在Default之后、文档之前仅一次PASS、真实exit0。
- [x] 两门Backend均2755/2755；statements10260/10523（97.50%），branches2101/2240（93.79%）。
- [x] 两门Frontend均52文件/634测试；statements3009/3121（96.41%），branches2812/3049（92.22%），functions721/726（99.31%），lines2904/2995（96.96%）。
- [x] 静态规则、类型检查、依赖完整性和production build均通过。
- [x] E2E重新枚举：development3、integration19（目录integrated）、startup-failure1，总计23/23。
- [x] DEV-001、INT-008/010/014/015/016/017/018/019等全部通过。
- [x] INT-019真实生产后端→LocalOpenAICompatibleProvider→受控loopback协议server，不是frontend mock；Continue/Rewrite未采用前正文不变，采用后Autosave与刷新持久化。
- [x] E2E端口释放、runtime数据无残留；未访问正式创作数据。
- [x] M6未增加Python/npm依赖；package.json/package-lock.json/backend配置依赖不变，不执行DependencyAudit、不伪造审计结果。
- [x] Windows local-first模块化单体；prefixed ULID、stable identity/immutable revision/head及乐观并发；无Git remote/push。

## Scope boundary / not implemented

以下能力未实现，是M6范围边界，不作为已完成用户能力勾选：

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

实际本机AI服务需另行配置；受控E2E不保证某个模型的文学质量。未改变浏览器draft恢复策略。原有5个后端弃用警告和Node颜色环境提示保留。

## 冻结操作合同

只新增三份M6文档；执行UTF-8、LF、final newline、严格JSON、secret/password/token/API key与绝对Windows路径扫描，以及Git diff --check和精确三文件暂存范围核验。扫描区分“未实现API key管理”等范围说明和真实秘密。

两门通过后仅做文档静态检查；不重复Default/IncludeE2E，不修改产品或测试。Acceptance主题固定 `docs(m6): accept ai writing foundation`，提交数53、跟踪文件698；annotated tag `m6-ai-writing-foundation` 消息固定 `M6 ai writing foundation accepted`，目标为验收提交。具体commit/tree、tag object/target/type/message、三份blob与最终冻结diff在执行报告记录，避免文档自引用。

M0–M5最终仍须保持原身份与18份冻结文档不变。最终main、worktree clean、staging empty、remote empty。M7未开始，无Export新代码、发布流程、M7文档或标签。
