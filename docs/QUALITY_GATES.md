# 本地质量门禁

质量门用于验证交付成果。当前执行方式：开发时运行受影响检查，提交前运行一次完整 `-IncludeE2E`（已包含 Default），结合隔离真实启动和作者流程；不把 RF 编号变成停点，不重复运行有效且代码未变的证据。门禁失败须修复，不降低测试或覆盖率。规则见 [稳定性协议](ACCEPTANCE_STABILITY.md)。

## 统一门禁

在仓库根目录执行默认门禁：

```powershell
.\scripts\quality_gate.ps1
```

脚本按以下顺序执行，任一步返回非零后立即停止，并保留该非零结果：

1. `git diff --check HEAD --`：检查当前差异中的空白错误；
2. 仓库卫生：只检查 Git 已跟踪文件中的本地产物、绝对用户路径和明显凭据；
3. 安全基线：只扫描 Git 已跟踪的生产代码和运行配置，拒绝危险静态模式并验证安全配置、中间件、CSRF、文档与 Uvicorn 策略接线；
4. 启动安全基线：静态拒绝按名称结束 Python/Node、自动安装、自动打开浏览器、仓库内 PID/日志和不安全进程清理模式；
5. Ruff 格式检查；
6. Ruff 静态规则；
7. mypy 严格类型检查；
8. 后端与架构测试，包括 Diagnostics、存储、安全、健康、启动脚本和依赖边界，并分别验证语句和分支覆盖率；
9. `pip check`：验证已安装 Python 依赖的一致性；
10. `npm run quality`：运行前端格式、lint、类型、覆盖率、测试和构建检查；
11. `npm ls --depth=0`：验证前端直接依赖树。

默认门禁不执行联网审计，网络不可用不应导致默认门禁失败。需要按任务要求审计生产依赖时，显式执行：

```powershell
.\scripts\quality_gate.ps1 -IncludeDependencyAudit
```

该模式在默认检查后增加 `npm audit --omit=dev`，可能访问 npm 网络服务。当前不引入 Python 联网漏洞扫描器。

脚本必须从仓库根目录运行，并要求根目录 `.venv`、前端 `node_modules`、64 位 Python 3.12 和 64 位 Node.js 24 已经可用。它不要求工作区干净，也不会格式化、暂存或提交文件。安全静态脚本按任务要求只读取 Git 已跟踪文件，因此完成前应先确认所有拟提交源码已处于暂存区；未跟踪的用户文件不会被读取。默认模式不会启动持久开发服务或浏览器，但后端测试会在各自的临时数据根中创建并清理测试目录和 SQLite，不得触碰正式 `%LOCALAPPDATA%\AIWebNovel`。

## 可选浏览器端到端验收

浏览器 E2E 需要本地 Chromium 缓存、真实服务进程和更长运行时间，因此默认门禁不执行。需要时显式运行：

```powershell
.\scripts\quality_gate.ps1 -IncludeE2E
.\scripts\quality_gate.ps1 -IncludeDependencyAudit -IncludeE2E
```

`-IncludeE2E` 在全部默认检查以及请求的依赖审计之后依次执行：

1. 检查本地 `@playwright/test` 对应的 Chromium 可执行文件；
2. 运行 `npm run e2e`，验收开发模式和生产集成模式；
3. 检查 E2E 专用端口已释放，场景自有数据根、数据库 sidecar、运行目录和成功产物均已清理。

门禁不会自动下载浏览器。浏览器缺失时明确失败，并提示在 `frontend` 目录运行 `npm run e2e:install`。E2E 失败或清理失败都会使统一门禁返回非零。运行方式、网络隔离和失败产物见 [浏览器端到端测试](E2E_TESTING.md)。

## Windows 专项与历史阶段入口

下述 DEV/M0 编号命令保留用于相应模块的精确追溯，不要求当前 AI 阶段机械重复旧阶段的整套门禁顺序。当前交付遵循页首规则；受影响的专项门槛仍保留。

DEV-0.8 还必须从仓库根目录单独执行：

```powershell
.\scripts\check_windows_storage.ps1
```

该脚本不属于默认门禁。它在 LocalAppData 下创建名称唯一的 `AIWebNovel-DEV-0.8-*` 临时兄弟目录，通过 `AIWEBNOVEL_DATA_ROOT` 启动真实 FastAPI，验证 12 个标准目录、`checks.storage=ok`、`checks.database=ok` 和派生数据库位置，然后终止自有进程并精确清理数据库、sidecar 和整个临时根。脚本只检查正式默认根是否存在，不读取其内容，也不修改 ACL；输出只包含临时根叶名，不包含本机绝对路径或用户名。

DEV-0.8 的完整验收顺序是：

```powershell
.\scripts\quality_gate.ps1
.\scripts\quality_gate.ps1 -IncludeE2E
.\scripts\quality_gate.ps1 -IncludeDependencyAudit -IncludeE2E
.\scripts\check_windows_storage.ps1
```

DEV-0.9 另有真实运行安全冒烟脚本：

```powershell
.\scripts\check_security_runtime.ps1
```

它使用独立数据根与临时环回端口验证 Host、代理头、请求限制、内容类型、会话 Cookie、CSRF、响应头、生产文档关闭和日志脱敏。该脚本不属于默认门禁，不能替代三种规定门禁；安全边界见 [本地应用安全基线](SECURITY_BASELINE.md)。

DEV-0.9 的完整验收顺序是：

```powershell
.\scripts\quality_gate.ps1
.\scripts\quality_gate.ps1 -IncludeE2E
.\scripts\quality_gate.ps1 -IncludeDependencyAudit -IncludeE2E
.\scripts\check_security_runtime.ps1
```

DEV-0.10 的 M0 预验收入口是：

```powershell
.\scripts\m0_preflight.ps1
```

它不是默认门禁的一部分，而是在工作区干净时固定执行 M0 诊断、默认门禁、带依赖审计及 E2E 的门禁、开发与集成启动烟测、存储与安全烟测、清理和 Git 复核。成功报告写入被 Git 忽略的 `.runtime/m0-preflight/`，结论只表示等待正式阶段验收，不宣告 M0 正式通过。

## 只运行后端检查

以下命令均从仓库根目录执行。显式指定配置文件，避免根目录运行时依赖工具的配置发现细节：

```powershell
.\.venv\Scripts\python.exe -m ruff format --check `
  --config backend/pyproject.toml `
  backend/src tests/backend tests/architecture

.\.venv\Scripts\python.exe -m ruff check `
  --config backend/pyproject.toml `
  backend/src tests/backend tests/architecture

.\.venv\Scripts\python.exe -m mypy `
  --config-file backend/pyproject.toml `
  backend/src/aiwebnovel

$coverageReport = Join-Path $env:TEMP `
  "aiwebnovel-backend-coverage-$PID-$([guid]::NewGuid().ToString('N')).json"
try {
  .\.venv\Scripts\python.exe -m pytest `
    tests/backend tests/architecture `
    --cov=aiwebnovel `
    --cov-branch `
    --cov-config=backend/pyproject.toml `
    --cov-report=term-missing `
    --cov-report="json:$coverageReport" `
    --cov-fail-under=0
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

  .\.venv\Scripts\python.exe scripts/check_backend_coverage.py $coverageReport
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
  Remove-Item -LiteralPath $coverageReport -Force -ErrorAction SilentlyContinue
}

.\.venv\Scripts\python.exe -m pip check
```

覆盖率 JSON 只写入系统临时目录，并在 `finally` 中删除。Python 检查器直接使用 coverage.py JSON 的计数，独立计算：

- `covered_lines / num_statements >= 80%`；
- `covered_branches / num_branches >= 75%`。

`--cov-fail-under=0` 避免 coverage.py 把语句和分支合并成一个百分比后误代替上述两个独立门槛；测试失败仍会返回非零，两个覆盖率门槛由检查器强制执行。

## 只运行前端检查

在 `frontend` 目录执行：

```powershell
npm run format:check
npm run lint
npm run typecheck
npm run test:coverage
npm run build
npm ls --depth=0
```

也可以用 `npm run quality` 顺序运行本项目定义的全部前端质量检查。前端覆盖率门槛为：statements 80%、branches 75%、functions 80%、lines 80%。仅在任务明确要求联网审计时另外运行 `npm audit --omit=dev`。

## 领域基础专项检查

DEV-1.1的纯`aiwebnovel.domain`模块除全局门槛外，还要求语句覆盖率不低于95%、分支覆盖率不低于90%。从仓库根目录对五个领域专项测试采集独立覆盖率；报告写入系统临时目录，分别按`covered_lines / num_statements`和`covered_branches / num_branches`计算并在检查后删除。专项测试包括标识与单调生成、UTC时间、修订号、并发版本和SQLAlchemy适配器。

该专项检查不替代默认质量门、E2E或依赖审计。领域层架构测试还会解析绝对、相对和间接导入，允许`db → domain`，拒绝`domain → db`、框架和其他第三方依赖。完整领域契约见[领域基础原语](DOMAIN_FOUNDATION.md)。

## Project基础专项检查

DEV-1.2及后续Project生产代码要求`aiwebnovel.project`语句覆盖率不低于95%、分支覆盖率不低于90%。DEV-1.5的Web专项覆盖严格DTO、ETag/If-Match、错误隐私、三个单Project接口、安全/CORS、OpenAPI、真实迁移数据库流程、未迁移安全失败和双会话HTTP并发。DEV-1.6的列表专项另覆盖应用Page不变量、专用Reader端口、单SELECT/无COUNT/无OFFSET、Keyset跨页稳定性、十类损坏、严格cursor、列表HTTP/OpenAPI、真实迁移库流程及`E2E-INT-007`；新增Project列表生产代码必须达到95%语句与90%分支覆盖率。

DEV-1.9的后端历史专项固定覆盖不可变读取模型与服务、专用HistoryReader、RevisionNumber降序Keyset分页、损坏数据、Project绑定cursor、两个只读HTTP接口、OpenAPI和真实迁移数据库链路。新增后端历史生产代码的statements/lines/functions均不低于95%，branches不低于90%；正式Project模块总覆盖率仍不得下降到95%语句或90%分支以下。

迁移、约束与Repository事务测试只能使用各测试拥有的临时SQLite数据库和隔离数据根，必须清理数据库、WAL、SHM、journal、受控测试触发器及Alembic运行产物。并发测试必须使用同一临时文件、两个独立Repository实例和Barrier同步，不得用sleep或全局Python锁决定顺序。专项结果不能替代默认门禁、两种E2E门禁或依赖审计；完整模型和事务边界见[Project持久化基础](PROJECT_FOUNDATION.md)与[Project Repository事务边界](PROJECT_REPOSITORY.md)。

## Project前端专项检查

DEV-1.7指定七组Vitest文件，覆盖Project API客户端、运行时契约、内存Security Session、列表、创建表单、页面组合与路由。新增`frontend/src/features/projects`生产代码要求statements/functions/lines均不低于95%，branches不低于90%；该专项门槛不能替代全量前端门槛。

DEV-1.8另固定七个详情专项文件：`project-etags`、`project-details-api`、`project-revise-api`、`project-details-page`、`project-edit-form`、`project-conflict-flow`和`project-detail-routes`。它们覆盖严格强ETag、GET无Session、PUT完整替换与单次发送、保存结果未知、412结构校验、显式读取/采用/重建基线及路由导航；新增详情生产代码要求statements/functions/lines均不低于95%，branches不低于90%。

DEV-1.9固定六个前端历史专项文件：`project-revision-history-contracts`、`project-revision-history-api`、`project-revision-history-list`、`project-revision-viewer`、`project-revision-history-page`和`project-revision-history-routes`。它们覆盖严格响应、GET无Session/CSRF、摘要分页、失败保留、按需正文、取消迟到请求、可访问性与路由；新增前端历史生产代码的statements/functions/lines均不低于95%，branches不低于90%。

ESLint受控正负样例保护`shared api → feature api → hooks → components → page → router`方向。安全静态门禁还拒绝CSRF/cursor/ETag/草稿/正文浏览器持久化、历史写请求或不必要Security Session、Project、Story Bible或Character POST/PUT自动重试与412自动重放、请求正文/cursor/Revision正文与`If-Match`日志、未编码业务ID路径、Revision写路由、外部API地址、不安全HTML、组件Cookie访问和组件硬编码CSRF。完整浏览器证据由`E2E-INT-008`至`E2E-INT-016`提供；`E2E-INT-011/012/013`验证Story Bible HTTP、当前前端与历史，`E2E-INT-014/015/016`验证Character HTTP、当前前端与只读历史。

## Story Bible专项检查

DEV-2.1的五组领域专项测试固定覆盖`sbl`/`sbr`规范标识、标题与50000代码点纯文本规则、Stable/Revision/Head/Aggregate不变量、初始创建、完整替换追加、stale优先级、时钟回退、强不可变性、100个Revision确定性序列和导入无副作用。新增`aiwebnovel.story_bible`生产代码要求statements为100%、branches不低于95%；专项覆盖率只采集该包，不能以全局覆盖率替代。

DEV-2.2的持久化专项覆盖精确六表Metadata、三种ORM Record、显式Mapper、Project唯一归属与RESTRICT外键、Head复合所有权外键、Revision检查/唯一约束、UPDATE/DELETE触发器、0002→0003→0002→0003迁移循环、Repository create/get/get_for_project/append、Stable与Head双CAS、固定副作用顺序、晚期失败回滚、损坏检测和确定性双实例并发。新增持久化与Repository生产代码要求statements不低于95%、branches不低于90%，原有纯领域覆盖率不得下降。

DEV-2.3的应用专项固定覆盖不可变原语命令/查询、Snapshot全部不变量、显式Mapper、创建与修订副作用顺序、Factory精确类型、Repository单次调用、按ID和按Project读取差异、错误隐私、真实Repository应用流程和双Command Service并发。新增`story_bible.application`生产代码要求statements为100%、branches不低于95%；完整Story Bible包中既有领域与持久化覆盖率不得下降。

DEV-2.5的前端专项固定覆盖严格11字段响应、共享规范ID和强ETag、创建与修订单次发送、写结果未知、412结构校验、草稿保留、显式读取/采用/重建基线、Project入口与精确路由、可访问状态及架构安全负向样例。新增`frontend/src/features/story-bible`生产代码的statements/functions/lines均不低于95%，branches不低于90%；`E2E-INT-012`还必须在真实迁移到0003的独立数据库验证UI创建v1、修订v2、外部v3、stale与手动v4，并验证不可变Revision、Head、Project不变和清理。

独立AST门禁扫描真实生产包，并以受控合法与非法模块证明：Story Bible纯领域与Repository契约只可依赖标准库、通用`domain`、Story Bible自身和`project.identifiers.ProjectId`；应用层只可增加对Repository契约的依赖；具体持久化适配器才可使用SQLAlchemy、通用`db`和只读Project ORM归属。FastAPI、Pydantic、Alembic运行时依赖、具体Repository、Project服务/Repository/Web、反向依赖、生产Fake/Spy及Story Bible表的跨模块直接写入均被拒绝。专项测试只访问自有临时数据库，不访问网络、正式数据根或真实系统时间，也不新增依赖；它不能替代默认、IncludeE2E及依赖审计加E2E三种完整门禁。

## Character专项检查

DEV-3.1的六组专项测试固定覆盖`chr`/`crv`严格规范标识、name/role/profile代码点与控制字符规则、Stable/Revision/Head/Aggregate全部不变量、无副作用初始创建、完整替换追加、stale优先级、clock rollback、强不可变性、100个Revision确定性序列、导入无副作用及AST架构正负样例。新增`aiwebnovel.character`生产代码要求statements为100%、branches不低于95%；专项覆盖率只采集该包，不能以全局覆盖率替代。

Character架构门禁只允许标准库、通用`domain`、Character自身和`project.identifiers.ProjectId`，拒绝框架、基础设施、Project其他层、Story Bible、Project/Story Bible/domain反向依赖和并存包名。该专项不访问数据库、网络、真实系统时间或正式数据根，不新增依赖，也不能替代默认、IncludeE2E及依赖审计加E2E三种完整门禁。

DEV-3.2持久化专项覆盖精确九表Metadata、三种Character ORM Record、显式Mapper、一Project多Character与非唯一索引、RESTRICT及Head复合所有权外键、Revision检查/唯一约束、总计六个Revision UPDATE/DELETE触发器、0003→0004→0003→0004迁移循环、Repository create/get/append、Stable与Head双CAS、stale优先级、晚期失败回滚、损坏检测和确定性双实例并发。新增Character持久化与Repository生产代码要求statements不低于95%、branches不低于90%，原有Character纯领域覆盖率不得下降。

DEV-3.2架构门禁区分纯领域、纯Repository契约和SQLAlchemy适配器：只有`character.persistence`可以依赖SQLAlchemy、通用DB适配层及只读Project Record；领域和契约不得导入具体适配器，Project、Story Bible和通用模块不得反向依赖Character。专项数据库必须迁移到0004并位于任务专属TEMP/TMP，结束后数据库、WAL、SHM和journal必须为0。

DEV-3.3应用专项覆盖不可变原语命令/查询、当前Snapshot、无profile列表摘要、Project绑定复合Position、严格Page不变量、显式Mapper、命令副作用顺序、Factory精确类型、写Repository与只读Reader单次调用、Project不存在与空列表区别、两SELECT上限、无COUNT/OFFSET/profile、Head权威、21个以上同时间Character稳定分页、真实应用流程和双Command Service并发。新增Character应用与列表读取生产代码要求statements不低于95%、branches不低于90%；命令、查询、模型与纯Mapper原则上statements为100%、branches不低于95%。专项结果不能替代默认、IncludeE2E及依赖审计加IncludeE2E三种完整门禁。

DEV-3.3架构门禁允许应用层依赖Character领域、写Repository契约和纯List Reader端口，但拒绝SQLAlchemy、具体Repository/List Reader、FastAPI、Pydantic、Story Bible与前端。只有`character.persistence.list_reader`可以反向实现应用列表端口；写Repository、领域、Project和Story Bible不得反向依赖Character应用层。导入应用与列表适配器不得连接数据库、创建文件、运行迁移、注册路由或改变九表Metadata。

## 显式格式化

格式化不是质量门禁的隐式步骤。需要改写格式时，在仓库根目录显式运行：

```powershell
.\scripts\format_code.ps1
```

该脚本只运行 Ruff 安全修复与格式化，以及前端 Prettier 格式化；它不会运行 `git add`、创建提交或修改锁文件。执行后必须人工审查 `git diff`，再重新运行统一门禁。

## 架构与仓库卫生

后端架构测试保护阶段0、M1 Project和DEV-2.1至DEV-2.5 Story Bible依赖方向。Project Web只可使用FastAPI、Pydantic、应用命令/查询/Snapshot/Page/服务契约和明确的Web工具；禁止SQLAlchemy、持久化模型、具体Repository/ListReader与Session。只有专用`project.persistence.listing`可向内依赖Project列表端口、模型与limit规则，其他持久化代码仍不得导入应用层。`main`作为组合根可以显式装配具体Repository、ListReader和应用服务。Story Bible领域、Repository契约与应用层保持纯Python，SQLAlchemy隔离在自身持久化适配器；Story Bible Web只可使用FastAPI、Pydantic、应用/领域公开类型与公共HTTP工具，禁止具体Repository、SQLAlchemy、Session、Clock和ID生成。前端受控样例保护共享API、Story Bible API、hook、组件、页面和Router的单向依赖，禁止业务组件绕过类型化客户端。其他模块仍不能写Story Bible三表。

仓库卫生脚本只使用 `git ls-files` 枚举并读取已跟踪文件，不读取未跟踪的用户文件。它发现疑似秘密时只输出仓库相对文件名和问题类型，不输出匹配值；不会自动删除文件，也不会改写 `.gitignore`。

安全静态脚本可单独从仓库根目录执行：

```powershell
.\scripts\check_security_baseline.ps1
```

它同样只通过 `git ls-files` 读取跟踪的生产代码和运行配置，不联网、不自动修复，也不打印匹配值。受控架构测试分别证明安全接线可通过、跟踪违规会非零失败、未跟踪文件不会被读取且 canary 不会进入输出。静态模式检查只是一层快速防回归，不能替代真实请求测试、E2E 或安全冒烟。

启动脚本静态安全检查可单独执行 `.\scripts\check_startup_safety.ps1`。它只检查版本库中的启动与诊断脚本，不启动服务，不按名称读取或终止系统进程，也不能替代真实启动、PID 所有权或清理烟测。

## 失败规则与当前边界

任何适用门禁失败，都不得声称当前任务完成，也不得开始下一编号任务。应先修复真实原因并完整重跑；不得降低阈值、跳过检查或把失败输出为成功。

安全静态门禁还检查Project、Story Bible和Character写路由无CSRF豁免、Router不导入SQLAlchemy/Session、历史路由无写方法、错误映射不输出异常正文、CORS不含PATCH/DELETE且显式暴露ETag/Location、DTO无Cookie/Session/Token字段。DEV-3.6新增Character历史生产代码要求statements至少95%、branches至少90%；前端历史代码要求statements/functions/lines至少95%、branches至少90%，cursor/模型/DTO/纯Mapper原则上100% statements且至少95% branches。27个ESLint受控非法导入样例保护前端方向。当前production API精确21条、前端路由精确10条，`E2E-INT-016`使完整E2E为20个。仍没有Character历史恢复/回滚/Diff/编辑/删除、关系/归档/结构化属性/AI生成，以及用户登录、搜索、写作、评审、Agent、Skill、Prompt、备份、导出或安装器。

DEV-2.7正式验收在任务专属TEMP/TMP中重新执行默认、IncludeE2E、依赖审计加IncludeE2E三种完整门禁并全部通过；17个E2E和npm生产依赖0漏洞均为M2冻结证据。后续任务不得通过降低阈值、删减场景或改写M2验收文件来改变该历史结论。
