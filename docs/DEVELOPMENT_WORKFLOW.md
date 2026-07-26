# 开发工作流

本文档规定 AIWebNovel 开发任务的基本执行纪律。全局规则以《AIWebNovel Codex全局开发说明 v1.0》为准。

## 任务纪律

1. 一次只执行一个编号任务，不并行实现其他编号任务的能力。
2. 每个任务必须明确列出允许修改范围、禁止修改范围、依赖、检查方法和完成定义。
3. 当前任务要求的测试或检查失败时，不得开始下一任务。
4. 不允许使用 TODO、假数据、空页面、空按钮、假进度或无真实后端行为的展示来声明任务完成。
5. 每个阶段结束时必须执行适用的回归测试和阶段验收；失败项解决前不得进入下一阶段。
6. Codex 执行任务后必须使用统一报告格式，准确区分完成、未完成和不适用项。
7. 开发数据库、测试数据库和作者的正式创作数据必须严格隔离；开发过程不得访问正式创作项目或正式备份。

## 本地数据隔离

应用的正式默认数据根是 `%LOCALAPPDATA%\AIWebNovel`。开发诊断、自动测试和 E2E 不得使用这个正式根：

- 统一开发和集成启动入口必须分别使用 `%LOCALAPPDATA%\AIWebNovel-Development` 与 `%LOCALAPPDATA%\AIWebNovel-Integrated-Development`，或由开发者显式指定安全的绝对隔离路径；
- 环境诊断只判断正式默认根是否存在，不得枚举或读取其内容；诊断读写与数据库探针必须使用 LocalAppData 下唯一临时根并在结束后清理；
- pytest 的应用工厂必须为每个测试使用独立临时数据根，没有显式临时根时测试辅助工厂必须拒绝启动；
- E2E 必须为每个场景创建带 E2E 标识的唯一临时数据根，并只清理该场景拥有的路径；
- 测试数据库必须位于该测试数据根的 `data/`，运行数据必须位于其 `runtime/`；
- 测试结束必须清理数据库、WAL、SHM、journal 和整个自有临时数据根；
- 不得通过回退到仓库、用户主目录或系统临时目录来掩盖正式配置错误。

DEV-0.8 的真实 Windows 存储冒烟验收是唯一受控例外。它只在 LocalAppData 下使用名称唯一的 `AIWebNovel-DEV-0.8-*` 兄弟目录，不读取、枚举、修改或删除正式 `AIWebNovel` 目录的内容。详细边界见 [本地存储](LOCAL_STORAGE.md)。

## 安全开发纪律

- 本地服务必须保持环回绑定，不得为了调试改为 LAN 或公网监听；
- 不得信任 `Forwarded` 或 `X-Forwarded-*`，也不得通过通配符放宽 Host 或 CORS；
- 新增不安全 API 方法默认继承请求体、JSON 内容类型、Origin、本地会话和 CSRF 保护，任何豁免必须在对应编号任务中逐路由说明与测试；
- 本地会话不是用户登录或业务授权，不得持久化到数据库或文件，CSRF 令牌不得进入浏览器持久存储；
- 不得记录请求正文、Cookie、Authorization、会话 ID、CSRF 令牌、完整查询字符串或其他秘密；
- 安全 ready、静态安全基线、受控负向测试、E2E 或真实冒烟失败时，不得通过放宽策略或跳过门禁继续。

完整威胁边界、Cookie、响应头、CSP 和当前明确缺失能力见 [本地应用安全基线](SECURITY_BASELINE.md)。

## 本地质量门禁

每个编号任务在声明完成前，必须从仓库根目录执行适用于当前基线的统一门禁：

```powershell
.\scripts\quality_gate.ps1
```

任一检查返回非零时，当前任务不得声明完成，也不得开始下一编号任务。需要联网审计 npm 生产依赖时，只在任务明确要求后执行 `.\scripts\quality_gate.ps1 -IncludeDependencyAudit`；默认门禁保持离线可运行。

质量门禁只检查而不改写代码。仓库卫生与安全基线只读取 Git 已跟踪文件；拟提交源码必须先按任务允许范围暂存并审查，未跟踪用户文件不会被扫描。需要格式化时应单独运行 `.\scripts\format_code.ps1`，人工审查差异后重新执行统一门禁。完整顺序、单项命令和覆盖率阈值见 [本地质量门禁](QUALITY_GATES.md)。

需要真实浏览器验收的任务必须显式运行 `.\scripts\quality_gate.ps1 -IncludeE2E`；如任务同时要求 npm 生产依赖审计，则运行 `.\scripts\quality_gate.ps1 -IncludeDependencyAudit -IncludeE2E`。浏览器缺失、E2E 失败、专用端口未释放或临时数据残留均视为门禁失败。默认门禁仍不启动浏览器，CI 和后续业务能力也不因 DEV-0.7 自动进入范围。E2E 细则见 [浏览器端到端测试](E2E_TESTING.md)。

DEV-0.8 还要求单独执行 `.\scripts\check_windows_storage.ps1`。该冒烟验收不属于默认门禁，也不代替三种规定的质量门禁。

DEV-0.9 还要求执行 `.\scripts\check_security_runtime.ps1` 的真实安全运行冒烟。它必须使用独立数据根和临时环回端口，验证安全失败路径、日志无秘密及进程、端口、数据库和临时文件清理；该冒烟同样不代替三种规定门禁。

DEV-0.10 提供 `.\scripts\environment_doctor.ps1`、统一启动脚本和 `.\scripts\m0_preflight.ps1`。环境诊断不会安装或自动修复软件；Development、Integrated 与 M0 模式的严格程度不同。M0 预验收按固定顺序组合诊断、门禁、真实启动、存储、安全与清理证据，失败即停止。预验收报告只能证明已准备等待正式阶段验收，不等于 M0 正式通过，也不能替代下一编号任务中的正式验收结论。

## M0冻结规则

DEV-0.1 至 DEV-0.11 已完成，阶段 0 工程底座已通过正式验收并冻结为 M0 基线。阶段1已经按独立DEV-1.x任务推进；M0通过不代表小说业务、Codex、Agent、Skill、Prompt或创作工作流已经实现。

冻结不表示基线永远不能修改。后续如需改变 M0 冻结边界，必须由明确的独立修复或演进任务授权，并同时说明修改原因与兼容性影响、重新运行所有相关门禁；不得重写或移动 M0 标签，也不得修改 M0 正式验收报告中的历史事实。

## 阶段1任务边界

阶段1已由独立的DEV-1.1任务开始，M0标签和三份正式验收历史文件继续保持冻结。DEV-1.1只建立无业务实体的领域标识、UTC时间、修订、乐观并发和持久化类型适配器；它不授权Project、业务表、迁移、Repository、API、页面、三区隔离或Codex能力。

后续DEV-1.x任务必须分别声明所属业务模块的前缀和数据所有权，不得把领域基础类型本身当作业务功能完成，也不得为了复用而让纯`domain`层依赖FastAPI、Pydantic、SQLAlchemy或其他基础设施。

DEV-1.2授权Project模块拥有稳定对象、不可变修订、独立Head指针以及`projects`、`project_revisions`、`project_heads`三表结构。它仍不授权Repository、Service、API、DTO、前端项目列表、删除归档、三区隔离或其他小说模块；应用启动不得自动执行0002迁移或创建Project数据。下一任务只有在独立授权后才能建立事务保存边界。

DEV-1.3授权Project所有者内部建立纯Python Repository契约与SQLAlchemy SQLite事务实现，只提供原子create、一致当前聚合get和带Project/Head双CAS的append_revision。它不授权应用Service、API、DTO、历史查询、删除、前端页面或Schema变化。关键事务测试必须使用迁移到head的独立临时数据库，证明`BEGIN IMMEDIATE`并发确定性、晚期失败完整回滚、损坏状态拒绝、Session关闭与sidecar清理；DEV-1.4只有在独立授权后才能建立应用命令和查询服务。

DEV-1.4授权Project内部建立不可变创建/修订命令、当前查询、脱离ORM的Snapshot和只依赖Repository契约的应用服务。每个写命令必须对应一次Repository事务，修订不得预先get，原始输入必须在任何可观测副作用前按规定顺序转换；真实集成测试继续使用迁移到0002的独立临时数据库并清理全部sidecar。该任务不授权HTTP API、Pydantic DTO、应用组合根接线、前端功能、列表、历史、删除或Schema变化；DEV-1.5只有在独立授权后才能建立Project HTTP边界。

DEV-1.5授权三个Project HTTP接口、严格Pydantic DTO、强ETag/If-Match、安全错误映射和组合根装配。写接口必须继承Origin、Session与CSRF，真实API与E2E只能显式迁移各自临时数据库；应用不得自动迁移。该任务不授权列表、历史、删除、归档、PATCH、前端Project页面或Schema变化；DEV-1.6仍需独立任务授权。

DEV-1.6授权独立Project列表读取模型与端口、SQLAlchemy单查询LEFT JOIN、按不可变`created_at + project_id`降序的Keyset分页、严格版本化cursor及列表GET。列表不返回description或total，不接受OFFSET/search/filter/sort；未迁移数据库必须安全503，损坏Project使整页失败。该任务不改变Schema或0002，不授权前端Project页面、历史、删除、归档、分支、审批或Codex能力；DEV-1.7仍需独立任务授权。

DEV-1.7授权React侧的类型化Project列表/创建客户端、精确运行时解析、仅内存Security Session、`/projects`页面、20项Keyset加载更多和创建后第一页刷新。列表GET不得获取Session，cursor保持不透明且不持久化，创建POST只发送一次；创建成功但刷新失败必须报告部分成功。该任务不改变后端、Schema或0002，也不授权详情、编辑、历史、删除、search/filter/sort/total或创作功能；DEV-1.8仍需独立任务授权。

DEV-1.8授权React侧的`/projects/:projectId`当前详情、强ETag绑定的编辑基线、完整替换PUT和显式412冲突恢复。详情GET不得获取Session；PUT只发送一次且不得预读、自动重试、自动重放或自动合并；冲突和保存结果未知都必须保留草稿并等待用户显式动作。该任务不改变后端、Schema或0002，也不授权历史、删除、归档、自动保存、Character、Chapter、三区、审批、Codex或其他创作功能；DEV-1.9仍需独立任务授权。

DEV-1.9授权Project不可变Revision历史的独立读取模型、Reader端口与SQLAlchemy适配器、两个只读GET、Project绑定的RevisionNumber Keyset cursor，以及`/projects/:projectId/history`页面和按需单Revision正文查看。历史GET不得获取Session或CSRF，列表不含description/total，cursor与正文不得进入浏览器存储或日志；Schema与0002保持冻结，不提供Revision写入、回滚、恢复、Diff、历史编辑或删除。DEV-1.10只有在独立授权后才能执行M1验收。

## M1冻结与阶段2任务边界

DEV-1.10已完成M1 Project基础能力正式验收，`m1-project-foundation`标签和三份M1验收文件与既有M0基线一同冻结。后续任务不得移动、覆盖或改写两个标签及其历史事实；发现缺陷必须使用新的编号任务和提交。

DEV-2.1只授权`aiwebnovel.story_bible`纯领域层：`sbl`/`sbr`标识、ProjectId归属引用、标题与纯文本正文值、稳定对象、不可变Revision、显式Head、一致Aggregate及无副作用创建/追加转换。它不授权Story Bible表、迁移、ORM、Repository、应用服务、DTO、API、前端、Character、World、PowerSystem、规划、三区、审批、Codex或Agent。DEV-2.2只有在独立任务明确授权后才能建立持久化能力；DEV-2.1的目录和对象不能被当作用户功能完成证据。

## 统一执行报告

任务报告至少包含：

1. 状态：完成或未完成；
2. 新增和修改文件清单；
3. 结构或行为变更摘要；
4. 相关文档用途或实现说明；
5. 实际执行的检查或测试命令；
6. 每项检查或测试结果；
7. 既有仓库冲突；
8. 未完成项；
9. 已知风险和限制；
10. 下一编号任务的前提是否满足。

只要任一适用的完成定义未满足，状态必须报告为“未完成”。不得通过跳过测试、降低门槛或省略失败项改变结论。
