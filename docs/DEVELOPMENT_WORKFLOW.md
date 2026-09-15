# 开发工作流入口

当前执行规则统一在 [AGENTS.md](../AGENTS.md)，当前状态在 [PLAN.md](../PLAN.md)。本页保留旧链接兼容，不再复制另一套授权、历史或失败处理规则。

一次交付一个已批准阶段：按内部依赖完成实现、测试、修复、文档及证据同步。阶段划分见 [交付路线](REFRACTOR_ROADMAP.md)；RF 细项不再各自制造对话停点。

按需使用：

- [质量门](QUALITY_GATES.md)：开发检查和适用命令。
- [稳定性协议](ACCEPTANCE_STABILITY.md)：精确候选与正式验收入口；正式失败仍须停止该轮。
- [本地启动](LOCAL_STARTUP.md)与[安全边界](SECURITY_BASELINE.md)：启动、隔离数据和安全约束。

M0–M7 逐项 DEV 记录保留于历史区，默认不读，不作为当前任务授权。
