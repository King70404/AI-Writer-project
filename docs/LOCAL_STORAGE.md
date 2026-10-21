# Windows 本地存储

本文档说明 DEV-0.8 建立的本地目录边界。它描述工程基础设施，不表示小说业务数据、文件上传、备份、导出、模型管理或文件日志已经实现。

## 默认数据根与数据库

应用从当前进程的 `LOCALAPPDATA` 环境变量解析唯一正式默认数据根：

```text
%LOCALAPPDATA%\AIWebNovel
```

第一版默认数据库文件由 `StoragePaths` 派生为：

```text
%LOCALAPPDATA%\AIWebNovel\data\aiwebnovel.sqlite3
```

正式数据不存放在 Git 仓库。旧的仓库相对 `.runtime/aiwebnovel-dev.sqlite3` 不再是默认值；应用不会自动读取、迁移或删除旧开发数据库，该工作必须由以后单独编号的迁移任务处理。

如果 `LOCALAPPDATA` 缺失、为空或无效，且没有显式合法覆盖，应用不会猜测其他目录，也不会回退到仓库、用户主目录或临时目录。

## 标准目录

存储初始化使用以下固定结构：

```text
AIWebNovel/
├── data/
├── assets/
├── runtime/
│   ├── app/
│   ├── temp/
│   └── locks/
├── models/
├── backups/
├── exports/
├── logs/
└── config/
```

- `data/`：SQLite 数据库及后续权威结构化数据；
- `assets/`：后续导入文件和内容寻址资产；
- `runtime/app/`：后续实例信息、崩溃恢复辅助信息和其他非权威运行状态；
- `runtime/temp/`：后续可删除的中间文件和短期产物；
- `runtime/locks/`：后续单实例、维护、迁移和恢复锁；
- `models/`：后续本地检测模型；
- `backups/`：作者手动创建的备份 ZIP（RF-15，格式与规则见 [作者备份](AUTHOR_BACKUP.md)）；
- `exports/`：后续用户主动导出的文件；
- `logs/`：后续本地诊断日志；
- `config/`：后续非敏感本地配置。

DEV-0.8 只创建这些目录。它不写入 `logs/`，不创建备份、导出、模型、配置、锁、沙箱或业务文件，也不实现自动临时文件清理或崩溃恢复。

## 路径配置与按需初始化

开发诊断、自动测试和 E2E 通过以下环境变量覆盖数据根：

```text
AIWEBNOVEL_DATA_ROOT
```

覆盖值必须是绝对路径；相对路径、空路径、空字节和规范化后的文件系统根会被拒绝。显式覆盖存在时不依赖 `LOCALAPPDATA`。`AIWEBNOVEL_DATABASE_URL` 如果显式提供，继续优先于从 `StoragePaths.database_file` 派生的 SQLite URL；该覆盖只用于受控开发、测试、迁移和诊断。

配置解析和模块导入都不创建目录。目录只在 FastAPI 生命周期启动阶段或显式调用存储初始化时按固定顺序创建。初始化可重复执行，不删除或清空已有内容；预期目录是普通文件、符号链接、junction 或其他重解析点时会失败且不会替换目标。初始化不创建数据库文件，数据库只在存储初始化与访问验证成功后由数据库层按需打开。

`StoragePaths` 是不可变路径集合。所有标准子路径都从规范化数据根派生，并使用路径边界判断保持在根内；调用方不得自行拼接核心路径。

## 访问能力与 Windows 权限边界

标准目录创建后，应用会在 `data/` 和 `runtime/temp/` 分别使用不可预测名称执行真实访问探针。探针以独占方式创建临时文件，写入非用户内容，刷新后重新读取并校验，再删除文件；失败时尽力清理。成功不会留下探针文件，API 和普通日志不会包含探针或数据根的完整路径。

当前版本依赖用户LocalAppData目录的Windows默认访问控制，并额外验证当前应用进程具备必要的读、写和删除能力。

应用不修改 ACL，不调用所有权或授权命令，不关闭继承，不授予 Everyone、Users 或匿名主体权限，也不要求管理员身份。当前检查不是全面 Windows ACL 审计，不应作为企业级权限认证；它只证明当前应用进程具备运行所需的实际访问能力。

## 运行时与权威数据

`runtime/` 只容纳可重建或短期运行数据。权威 SQLite 数据库位于 `data/`；备份、导出和模型分别位于 `backups/`、`exports/` 和 `models/`，不得放入 `runtime/`。备份创建与校验的中间快照只短暂写入 `runtime/temp/`，操作结束即删除。

作者备份只包含 `data/aiwebnovel.sqlite3` 的一致快照，不包含 `config/` 中的模型配置或 Key。恢复从不写当前数据根，而是在新的或空的文件夹中建立独立数据根，见 [作者备份](AUTHOR_BACKUP.md)。

DEV-0.8 仅区分 `runtime/app`、`runtime/temp` 和 `runtime/locks` 并创建空目录，不实现单实例锁、锁协议、任务沙箱、临时文件清理或崩溃恢复。

## 开发、测试与 E2E 隔离

开发启动必须显式设置独立的绝对 `AIWEBNOVEL_DATA_ROOT`。每个自动测试使用独立临时数据根；测试辅助工厂在没有显式临时根时拒绝启动。每个 E2E 场景也使用带 E2E 标识的唯一临时根，其数据库位于 `data/`，应用运行目录位于 `runtime/`。

测试不得读取或扫描正式 `%LOCALAPPDATA%\AIWebNovel`。结束时必须清理场景自有数据库、WAL、SHM、journal 和整个临时根；清理只针对该场景记录并验证过的精确路径，不能按模糊名称删除。

真实 Windows 冒烟验收使用 LocalAppData 下名称唯一的 `AIWebNovel-DEV-0.8-*` 兄弟目录。它只检查正式默认根是否存在，不读取其内容，不修改其元数据或权限，也不删除它。

## live 与 ready

`GET /api/v1/health/live` 表示后端进程仍能响应。存储配置或初始化失败时，应用仍尽量让 live 返回 200。

`GET /api/v1/health/ready` 表示应用可以安全处理依赖本地存储的请求。成功响应包含：

```json
{
  "status": "ready",
  "checks": {
    "configuration": "ok",
    "application": "ok",
    "storage": "ok",
    "database": "ok",
    "frontend": "not_required"
  }
}
```

生产静态模式下 `frontend` 可以为 `ok`。存储失败时 ready 返回 503，`status` 为 `not_ready`，`checks.storage` 和 `checks.database` 统一为 `failed`。响应不会返回数据根、数据库文件、探针文件、链接目标、Windows 用户名、ACL 或底层系统异常。现有 `SystemStatus` 将其归类为“本地后端可访问，但尚未就绪”，而不是网络不可用。
