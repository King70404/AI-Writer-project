# 本地应用安全基线

本文档描述 DEV-0.9 为阶段 0 本地应用建立的安全边界。它是本地单用户应用的基础防护，不是用户身份认证、企业安全方案或小说业务授权系统。

## 威胁边界

第一版只接受本机浏览器通过 HTTP 访问本机 FastAPI。基线重点防止服务意外暴露到局域网、恶意 Host 与跨站请求、过大或错误类型的 API 正文、秘密进入日志，以及生产接口文档和浏览器页面缺少基本响应限制。

应用默认只绑定 `127.0.0.1`，不支持 LAN 或公网访问，也不把非环回配置静默改写成环回后继续。当前不提供 HTTPS、反向代理、企业级身份认证、用户账号、密码、JWT、OAuth 服务端、API Key、速率限制、全面 Windows ACL 治理或数据加密。具备当前用户权限的恶意本机进程、管理员和已攻陷操作系统不在本基线能够隔离的范围内。

## 主机、代理与 CORS

- 默认可信 Host 只有 `127.0.0.1` 和 `localhost`；端口在解析后单独验证，空值、重复 Host、控制字符、凭据、非法端口、通配符和后缀欺骗均拒绝。
- Host 拒绝返回 HTTP 400 与固定错误码 `INVALID_HOST`，保留安全的 request ID，但不回显恶意原值。
- Uvicorn 显式使用 `proxy_headers=False`，不会使用 `Forwarded` 或 `X-Forwarded-*` 决定 Host、scheme、客户端来源或同源关系。
- 开发 CORS 只允许配置中明确列出的本地 HTTP(S) origin，方法精确为GET、POST、PUT、OPTIONS；允许必要的Content-Type、CSRF、If-Match和request ID Header，并暴露request ID、ETag和Location。禁止PATCH、DELETE、通配符和跨域凭据。生产静态服务使用同源相对 API。
- 安全 ready 会检查监听 Host、可信 Host、CORS、代理头策略及中间件注册；关键项失败时 live 仍可用于进程探测，但 ready 返回 503 且 `security=failed`。

## 请求限制与内容类型

`/api/` 下 POST、PUT、PATCH、DELETE 默认正文上限为 1 MiB。中间件既检查合法 `Content-Length`，也在 ASGI receive 流中累计实际字节，因此缺少长度、分块传输或声明长度小于实际长度仍会受到限制。超限返回 HTTP 413 与 `REQUEST_TOO_LARGE`，停止继续读取，不记录正文，也不创建临时文件。

带非空正文的普通结构化 API 请求只接受 `application/json` 或 `application/*+json`，允许合法 charset 参数。缺少或不支持的类型返回 HTTP 415 与 `UNSUPPORTED_MEDIA_TYPE`。空正文、健康检查和静态文件不受内容类型规则影响；当前没有上传接口，后续 multipart 只能通过明确的路由级审查引入。

## 本地临时会话

`GET /api/v1/security/session` 创建无账号的本机浏览器临时会话。它不是登录、身份认证或业务授权：

- 会话 ID 与 CSRF 令牌使用相互独立的密码学安全随机值；
- 会话只保存在当前应用进程内存，不写数据库或磁盘，应用重启即失效；
- 服务端保存用于安全比较的 CSRF 摘要，不在诊断或日志中暴露令牌；
- 默认有效期为 28,800 秒，默认最多保存 16 项；访问时检查过期，达到上限时先清理过期项，再按确定性最旧项策略淘汰；
- 响应使用 `Cache-Control: no-store`，CSRF 令牌只在响应 JSON 中返回；前端安全客户端只在模块内存持有，不写 `localStorage` 或 `sessionStorage`，页面也不显示它。

默认 Cookie 名为 `aiwebnovel_session`，属性为 `HttpOnly`、`SameSite=Strict`、`Path=/api` 和与会话 TTL 对应的 `Max-Age`，不设置 `Domain`。当前本地 HTTP 不伪装设置 `Secure`；将来只有真实 HTTPS 方案才能启用该属性。

## Origin 与 CSRF

所有未来不安全 API 方法默认经过 CSRF 中间件。除创建会话的内部入口外，POST、PUT、PATCH、DELETE 必须同时具备：合法 Host、允许的 Origin、有效且未过期的会话 Cookie，以及与该会话匹配的配置头（默认 `X-CSRF-Token`）。令牌比较采用常量时间路径。

外部、`null`、带凭据、非 HTTP(S) 或缺失的浏览器式 Origin 均拒绝；GET、HEAD、OPTIONS 不要求 CSRF，CORS 预检不会被会话校验阻断。Project POST和PUT完整继承该保护，不存在路由豁免；失败不回显Cookie、令牌或“正确值”。Project验证、并发和持久化错误只返回固定安全摘要与request ID，不返回正文、SQL、数据库路径或异常原文。

## 响应头、CSP 与 API 文档

所有响应包含 `X-Content-Type-Options: nosniff`、`Referrer-Policy: no-referrer`、`X-Frame-Options: DENY`、`Cross-Origin-Opener-Policy: same-origin` 及限制摄像头、麦克风、定位、支付和 USB 的 `Permissions-Policy`。API 响应额外使用 `Cache-Control: no-store`。

HTML 使用只允许本地构建资源的 CSP：默认、脚本、样式、字体和连接来源限制为 `'self'`，图片额外允许 `data:`，并禁止 object、base、外部 frame 与非同源 form。策略不使用 `unsafe-eval`、`unsafe-inline` 或外部 CDN。Uvicorn 关闭 Server 版本头。

development/test 可通过配置开启 `/docs`、`/redoc` 和 `/openapi.json`；两个 HTML 入口只提供遵守 CSP 的本地 Schema 索引，不引用外部 CDN，production 默认关闭，关闭路径及其子路径不会进入 SPA 回退。接口文档不应包含秘密配置，但生产仍按最小暴露原则关闭。

## 日志脱敏

集中脱敏覆盖大小写不同的 Authorization、Cookie、Set-Cookie、CSRF 头、会话 Cookie 名、access/refresh token、password、secret 与 api_key。脱敏不修改原对象，只输出固定占位符，不保留长度、前后缀、请求正文或完整查询字符串；无法序列化的对象也不能使日志崩溃。自动测试使用受控 canary 证明请求、异常、Header、Cookie、CSRF 失败和结构化附加字段均不泄漏原值，测试报告本身也不得打印 canary。

## 验证与开发纪律

默认质量门禁在仓库卫生之后运行 `scripts/check_security_baseline.ps1`。该脚本只读取 `git ls-files` 返回的生产代码和运行配置，检查危险静态模式及应用工厂安全注册；它不联网、不自动修复，也不打印疑似秘密值。受控正负测试证明安全仓库通过、跟踪违规失败、未跟踪用户文件不被读取。静态检查不能替代后端运行测试、浏览器 E2E 和真实 Windows 安全冒烟。

可从仓库根目录单独执行：

```powershell
.\scripts\check_security_baseline.ps1
.\scripts\check_security_runtime.ps1
```

后者使用独立临时数据根和动态环回端口启动 production 服务，完成实际 Host、响应头、会话、限制、日志和清理验收；它不读取正式用户数据。

任何安全配置、静态检查、运行测试、CSP页面验收或清理检查失败，都不得绕过门禁或开始下一编号任务。当前受保护写接口包括Project创建/完整修订与Story Bible创建/完整修订；全部继承相同的Host、可信Origin、进程内Session、CSRF、JSON媒体类型、1 MiB正文限制、request ID和安全响应头。Story Bible GET不要求Session或CSRF，所有Story Bible成功响应均`no-store`，写入正文和If-Match不进入日志。仍没有上传、用户登录、安全设置页面、Codex沙箱或全面ACL治理。
