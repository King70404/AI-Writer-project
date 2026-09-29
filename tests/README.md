# 测试入口

- `backend/`：领域、持久化、HTTP、迁移与集成测试。
- `frontend/`：API 契约、界面、编辑状态和并发处理。
- `architecture/`：模块依赖、安全边界、仓库卫生和脚本行为。
- `e2e/`：真实后端与 Chromium 的完整浏览器流程。

完整开发检查从仓库根目录运行：

```powershell
.\scripts\quality_gate.ps1
.\scripts\quality_gate.ps1 -IncludeE2E
```

Default 不包含浏览器；第二条会先执行 Default，再运行完整 E2E。模块改动先运行相关用例，交接时执行任务要求的完整门禁。命令、覆盖率及失败处理见 [质量门禁](../docs/QUALITY_GATES.md)；单项浏览器入口和失败证据见 [E2E 说明](../docs/E2E_TESTING.md)。

测试必须使用自己创建的隔离数据根并清理自有资源，不得访问作者正式创作数据。部分回归会读取固定路径的历史验收清单或 Manifest 作为契约；这些文件由程序按需读取，不要求代理每次任务通读历史。
