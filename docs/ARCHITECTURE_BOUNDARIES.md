# 架构边界

本文档记录 AIWebNovel 的高层模块边界、阶段 0 后端基础设施，以及阶段 1 通用领域与Project内部持久化基础的依赖方向。边界说明不代表用户已经可以管理或保存小说项目。

## 业务模块

- Project
- Market
- StoryBible
- Planning
- Writing
- Review
- Canon
- Style
- Analytics
- Workflow

## 基础设施模块

- Assets
- Search
- CodexRuntime
- Infrastructure

## 阶段 0 后端基础设施分层

当前后端由以下基础层组成：

- `core`：类型化配置、通用错误、日志和中间件；
- `storage`：不可变 `StoragePaths`、标准目录初始化、重解析点检查、访问探针和存储健康结果；
- `db`：SQLite 引擎、会话与数据库健康检查；
- `security`：环回和 Host 策略、请求限制、本地临时会话、Origin/CSRF、安全响应头、脱敏及安全健康结果；
- `diagnostics`：组合公开的配置、存储、数据库和安全诊断契约，产生稳定且脱敏的环境检查结果；
- `web`：HTTP 与前端静态服务适配；
- `main`：组合 `core`、`storage`、`db`、`security` 和 `web` 的应用组合根。

允许的依赖方向：

- `storage` 可以导入 `core` 的公开配置契约；
- `db` 可以读取公开的 `StoragePaths` 契约或由组合根传入的配置；
- `db` 不得导入 `storage` 的目录初始化、访问探针或健康检查实现；
- `security` 可以导入 `core` 的公开配置和错误契约；
- `diagnostics` 可以导入公开的 `core`、`storage`、`db` 和 `security` 诊断契约；
- `web` 只能使用 Security 的公开 DTO 或响应工具，不得访问会话内部存储；
- `main` 可以组合 `core`、`storage`、`db`、`security` 和 `web`；
- PowerShell 环境与启动脚本可以调用 Diagnostics 命令入口；
- 生产代码不得导入测试临时路径工具。

阶段 0 后端的明确禁止：

- `core` 不得导入 `storage`、`db`、`security`、`diagnostics`、`web` 或 `main`；
- `storage` 不得导入 `db`、`security`、`diagnostics`、`web` 或 `main`；
- `db`、`security` 和 `web` 不得导入 `diagnostics`；
- `security` 不得导入 `storage`、`db`、`web` 或 `main`；
- `diagnostics` 不得导入 `web` 或 `main`，不得访问 Security 会话内部存储；
- `diagnostics` 不得修改业务数据、创建正式项目、枚举正式数据根或输出秘密；
- `web` 不得直接导入 `storage` 或访问其内部文件操作；
- `web` 不得导入 Security 的会话、CSRF 或中间件内部实现；
- `db` 不得访问会话或 CSRF，Security 会话管理器不得写入数据库或文件；
- `db` 不得自行读取或重新推导 LocalAppData 路径；
- 除 `core` 的配置边界外，其他生产模块不得硬编码 LocalAppData 数据根；
- `core`、`storage`、`db`、`security`、`diagnostics` 和 `web` 不得反向导入组合根；
- 应用组合根 `main` 不依赖 Diagnostics；
- 各层不得形成循环依赖。

`StoragePaths` 是路径契约，不是新的业务数据所有者。`storage` 只管理本地目录边界和访问能力，`db` 仍负责 SQLite；两者都不得创建小说业务表或业务 Repository。

Security 是请求边界而不是身份或业务权限所有者。本地会话只存在于进程内存，不能写入 SQLite 或文件；CSRF 只保护 HTTP 请求完整性，不等于用户登录，也不授予 Canon 或其他业务权限。生产代码不得导入测试安全路由。

## 阶段 1 纯领域基础层

`domain`保存不依赖框架的标识、UTC时间、修订号、并发版本和领域错误。它只允许导入Python标准库及自己的子模块，不得导入`core`、`storage`、`db`、`security`、`diagnostics`、`web`、`main`、FastAPI、Pydantic或SQLAlchemy。

允许的方向是`db → domain`：`db/types.py`可以把领域值适配为SQL标量，但适配器不拥有领域规则，也不得创建正式表。`core`不得反向依赖领域类型；生产源码不得从测试目录取得前缀、时钟或随机源。绝对、相对和经`aiwebnovel`包间接导入都受同一AST架构门禁约束。

DEV-1.1建立的通用原语不拥有任何业务前缀或表，也不反向依赖Project。详细契约见[领域基础原语](DOMAIN_FOUNDATION.md)。

## 阶段1 Project模块

`project.identifiers`、`project.values`、`project.entities`、`project.transitions`和`project.errors`组成纯业务领域部分，只能依赖Python标准库、通用`domain`和Project自身领域模块。它们不得导入SQLAlchemy、FastAPI、Pydantic、`db`、`core`、`storage`、`security`、`diagnostics`、`web`、`main`或测试代码。

`project.persistence`是Project拥有的外向数据库适配层，可以导入Project领域契约、SQLAlchemy以及公开的`db.base`和`db.types`，但不能导入Web、Security、Storage、Diagnostics、Main或测试代码。它只定义ORM记录与显式双向mapper，不提供Repository、Session生命周期、自动提交或查询服务。

`db.model_registry`是模型组合入口，可以确定性导入`project.persistence.models`并返回正式`Base.metadata`；这是通用DB指向Project持久化实现的唯一受控例外。`db.types`、`db.base`和其他通用DB模块不得导入Project，`core`与通用`domain`也不得反向依赖Project。模型注册不连接数据库、不执行迁移，普通Project领域导入不加载SQLAlchemy。

Project唯一拥有`projects`、`project_revisions`和`project_heads`。其他模块不得直接写这些表；后续跨模块访问必须经过Project公开应用服务。本任务没有建立该服务，也没有Project API、DTO或前端页面。完整结构与事务边界见[Project持久化基础](PROJECT_FOUNDATION.md)。

## 所有权与跨模块规则

- 每类数据只能有一个权威所有者，其他模块不得绕过所有者直接读写其内部存储。
- 跨模块调用只能通过公开应用服务并使用版本化 DTO；需要跨模块传播的领域变化使用持久化领域事件。
- 模块内部 Repository、数据库表和实现细节不属于公开契约。

## 明确禁止

- Writing 不得直接写入 Canon。
- Review 不得直接修改正文。
- Planning 不得直接修改正式状态或正式事实。
- Style 不得直接修改正文。
- Market 或 Analytics 不得自动改变正式项目。
- Workflow 不得直接写业务表，必须通过公开应用服务编排业务操作。
- CodexRuntime 不得访问业务 Repository。
- Search 只用于召回，不是正式事实来源。
- UI 不得直接访问 SQLite，必须通过后端公开接口与应用服务访问业务能力。
