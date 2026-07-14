# 测试目录

本目录存放当前工程基础的后端、前端和确定性架构测试：

- `backend/` 使用 pytest 验证 FastAPI、配置、数据库、迁移和静态服务；
- `frontend/` 使用 Vitest 验证 API 客户端、组件、路由和前端分层规则；
- `architecture/` 使用 AST、临时 Git 仓库和受控子进程验证架构边界、仓库卫生与质量门禁失败传播。

pytest 已登记 `unit`、`integration` 和 `architecture` 标记，并启用严格标记检查。当前没有浏览器端到端测试；该能力属于后续 DEV-0.7。统一执行方式和覆盖率门槛见 [本地质量门禁](../docs/QUALITY_GATES.md)。这些测试只验证工程底座，不表示小说业务功能已经实现。
