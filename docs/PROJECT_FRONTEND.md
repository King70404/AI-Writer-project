# Project 前端列表与创建流程

DEV-1.7 在不改变后端 API、数据库 Schema 或 `0002_create_project_foundation` 迁移的前提下，提供真实的 React Project 列表与创建流程。页面入口是 `/projects`；当前只支持读取第一页、使用不透明 Keyset cursor 加载更多、手动重新加载和创建 Project。

## 模块与网络边界

`frontend/src/features/projects/` 按 `api`、`hooks`、`components` 和 `pages` 分层。Project API 客户端复用通用同源 `fetch` 传输能力，并提供 `listProjects` 与 `createProject`；组件不直接调用 `fetch`、读取 Cookie 或获取 CSRF。请求始终使用相对 `/api/v1`，前端不包含外部 API 主机。

所有 Project、列表、错误和 Security Session 响应都经过精确的运行时结构校验。未知字段、缺失字段、非法 ID、非正整数版本、naive 时间、重复 Project ID 或 `has_more`/cursor 不一致都会使整个响应失败，非法数据不会进入 UI。错误 UI只使用安全分类、固定说明和经过字符约束的 request ID，不显示后端正文、CSRF、Cookie 或异常文本。

## 列表状态与 Keyset 加载

列表明确区分初始 loading、成功空列表、初始错误和成功列表；只有 API 成功返回空 `items` 才显示空状态。初始失败可重新读取第一页。每个列表项只显示标题、Project ID、当前 RevisionNumber、ConcurrencyVersion、创建时间和更新时间。

列表固定以 `limit=20` 请求。`next_cursor` 是后端拥有的不透明字符串：前端只使用 `URLSearchParams` 原样传回，不解码、不修改、不写入 URL 或浏览器存储。加载更多期间按钮禁用；成功时追加项目，失败时保留原 items 与 cursor 并允许手动重试；跨页重复 ID 被视为契约错误。最后一页不显示加载更多。

列表不显示 `description`，因为简介不是识别当前 Project 与分页所需的摘要字段，且最大可达 2000 个 Unicode 代码点；列表 API 本身也不返回该字段。当前也没有 `total`、OFFSET、search、filter 或自定义 sort。

## 创建、安全与状态语义

创建表单字段精确为 `title` 与 `description`。标题必填且最多 120 个 Unicode 代码点，简介可空且最多 2000 个 Unicode 代码点；emoji按一个代码点计数。客户端校验用于即时反馈，后端领域验证始终是权威来源。无效输入不会获取 Session、发送 POST 或刷新列表。

创建前由 Project Security Session 管理器按需取得 `/api/v1/security/session`。CSRF 仅保存在模块内存，带 30 秒安全窗口复用；并发获取合并为一个请求，失败不缓存，401/403及安全错误会清除缓存。令牌不进入 `localStorage`、`sessionStorage`、DOM、URL、日志或诊断文本。HttpOnly Session Cookie 仍由浏览器同源管理，前端代码不读取它。

`createProject`只发送一次同源 JSON POST，不自动重试。这样可避免服务器已经创建成功、但响应在客户端丢失时重复创建 Project。提交期间表单禁用并阻止重复触发；POST失败保留输入。POST成功后清空表单并重新读取不带旧 cursor 的第一页。

如果 POST 已成功但第一页刷新失败，UI显示“已创建但列表刷新失败”的部分成功状态、规范 Project ID和手动重新加载入口；它不会误报创建失败，也不会再次 POST。

## 可访问性与当前限制

页面使用关联 label、语义化 `ul`/`li`、`time`、明确的 loading/status/alert、提交禁用和成功或错误后的焦点管理。窄屏布局保持表单、列表和操作可读，页面不依赖颜色单独表达状态。

当前没有 Project 详情路由、修订编辑、PUT 前端调用、历史、删除、归档、恢复、搜索、筛选、自动保存或创作工作台。DEV-1.8 的范围必须由独立任务明确授权；本文件不预先声明其能力。

## 验证证据

七组 Project 前端 Vitest 专项覆盖 API、运行时契约、内存 Session、列表、创建表单、页面组合和路由。受控 ESLint 与安全静态测试验证依赖方向、无浏览器令牌/cursor持久化、无 POST 自动重试、无请求正文日志、无外部 API 和无不安全 HTML。`E2E-INT-008`在真实 production 集成服务与显式迁移的临时 SQLite 上验证创建、刷新持久性、21项加载更多、三表行数、CSP、浏览器存储和清理。
