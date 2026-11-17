# A1-1 模型连接检查：Windows 验证

- 代码提交：`ae23efaefedaed5aad0a8924565e4a6475c8d0bb`，基于 main `dea6eafc53f92eab6a1d19b8be6017af902d97c4`。
- `scripts/quality_gate.ps1 -IncludeE2E`：退出码 0。后端 3,271 项通过，语句/分支覆盖率 97.70%/92.90%；前端 79 文件、1,078 项通过，语句/分支/函数/行覆盖率 94.14%/90.00%/95.90%/95.32%；E2E 34 场景及自有数据、端口清理检查通过。
- 本机日志 `.runtime/a1-1-recovered-gate-20261109.log` 的 SHA-256：`3E097C84CDC8E8FD555CDD4AEF7CA3598B6FAC038E921FFF0CE53A95A378CBB6`。
- 本机工作树的 Python 源码隔离配置修正后重跑整套；此前由于测试子进程源码路径被隔离配置覆盖而失败的日志保留在 `.runtime/`。运行使用隔离测试数据和假传输，没有使用真实模型、Key 或正式创作数据。
- 依赖诊断中的既有 Starlette 弃用提示以及构建和浏览器工具输出保留在日志中；不把本次工程验证当作真实模型服务质量验收。

## 2026-11-18 同步已合并 A1-2

同步 main `67d1ca3`（含 PR #43 merge `530a8ce`），冲突只在 PLAN；未手工修改运行时代码或测试。原 A1-1 完整门禁证据保留，不声称同步后的 head 重新跑过整套门禁。

受影响补验通过：模型连接后端 22 项；前端模型连接、规划保存、工作台和规则相关 5 文件共 60 项；TypeScript 类型、变动文件 Prettier 和 ESLint；E2E-INT-019、E2E-INT-023 及清理检查。日志分别为 `.runtime/a1-1-main-sync-E2E-INT-019-20261118.log` 和 `.runtime/a1-1-main-sync-E2E-INT-023-20261118.log`。仅假传输及隔离数据。

PR #44 尚未合并，等待用户单独授权。
