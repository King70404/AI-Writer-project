# 架构边界

本文档记录 AIWebNovel 的高层模块边界，以及阶段 0 后端基础设施的依赖方向。边界说明不代表小说业务模块已经实现。

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
