# 后端开发

`src/aiwebnovel/` 是 FastAPI 应用与领域模块；`alembic/` 保存数据库迁移。项目状态和任务顺序见根目录 [PLAN.md](../PLAN.md)，本页只提供后端操作入口。

使用 Windows、64 位 Python 3.12。在仓库根目录首次准备开发环境：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "backend[dev]"
```

日常启动和后端测试也从仓库根目录执行：

```powershell
.\scripts\start_development.ps1
.\.venv\Scripts\python.exe -m pytest tests/backend tests/architecture
```

Development 默认使用 `%LOCALAPPDATA%\AIWebNovel-Development`，服务只绑定环回地址。测试由夹具创建隔离数据库，不得读取或改写作者正式数据。

普通无参数 `start_integrated.ps1` 使用正式 `%LOCALAPPDATA%\AIWebNovel`。集成启动只为不存在的数据库创建文件并迁移；已有数据库保持原样。开发、测试或 smoke 使用集成启动时必须显式指定任务自有的隔离 `-DataRoot`。

按需查阅：

- [启动与数据根](../docs/LOCAL_STARTUP.md)、[存储边界](../docs/LOCAL_STORAGE.md)：启动、停止和数据库操作。
- [质量门禁](../docs/QUALITY_GATES.md)：格式、静态检查、类型检查、测试与覆盖率。
- [架构边界](../docs/ARCHITECTURE_BOUNDARIES.md)、[安全边界](../docs/SECURITY_BASELINE.md)：修改相关模块时读取；精确依赖规则同时受 `tests/architecture/` 检查。
