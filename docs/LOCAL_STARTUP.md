# 本地统一启动

仓库提供开发模式和普通本地 V1 / 集成模式两个前台启动入口。两者都只绑定 loopback；开发、自动测试和验收必须与作者正式创作数据保持隔离。

## 普通作者：双击启动

在仓库根目录直接双击：

```text
启动 AI 网文助手.cmd
```

该入口会：

- 自动切换到仓库根目录；
- 复用 `scripts/start_integrated.ps1` 的正式数据根、端口、环境诊断和受控进程边界；
- 等待 `http://127.0.0.1:8000/api/v1/health/ready` 真正返回 ready 后，再用系统默认浏览器打开 `http://127.0.0.1:8000/`；
- 保持启动窗口在前台，用户写完后仍通过 `Ctrl+C` 安全停止本次拥有的服务进程。

如果启动失败，窗口会保留错误信息，不会自动删除、迁移或重置已有正式数据。双击入口只是普通用户壳层，不改变 integrated 启动脚本的正式安全边界。

## 开发模式

```powershell
.\scripts\start_development.ps1
.\scripts\start_development.ps1 -BackendPort 8001 -FrontendPort 5174
.\scripts\start_development.ps1 -DataRoot <绝对开发数据根>
```

默认行为：

- FastAPI 绑定 `127.0.0.1:8000`；
- Vite 绑定 `127.0.0.1:5173`；
- Vite 代理指向本次指定的后端端口；
- 数据根为 `%LOCALAPPDATA%\AIWebNovel-Development`；
- 启动前执行 `Development` 模式环境诊断。

`-NoPreflight` 只跳过普通诊断，Python、Node、端口和数据根安全检查仍会执行。脚本不会安装依赖、自动迁移正式数据库或自动打开浏览器。

开发模式不得使用正式 `%LOCALAPPDATA%\AIWebNovel` 及与其不安全重叠的路径。

## 普通本地 V1 / 集成模式

```powershell
.\scripts\start_integrated.ps1
.\scripts\start_integrated.ps1 -Port 8001
.\scripts\start_integrated.ps1 -BuildFrontend
.\scripts\start_integrated.ps1 -DataRoot <安全的绝对数据根>
```

默认只启动 FastAPI，由其提供已有的 `frontend/dist`，绑定 `127.0.0.1:8000`。运行环境固定为 production，API 文档默认关闭。

**无 `-DataRoot` 时，当前默认数据根是正式 `%LOCALAPPDATA%\AIWebNovel`。** 这是普通本地 V1 启动路径；不要把它当作自动测试、E2E 或 smoke 的数据根。

启动会调用 `scripts/initialize_integrated_database.py`：

- 数据库文件不存在时，初始化器使用独占创建建立一个新数据库，然后执行 Alembic `upgrade head`；
- 数据库文件已经存在时，初始化器立即保留现状，不迁移、不替换、不删除、不重置已有数据；
- 首次迁移失败时保留失败数据库供检查，后续启动不会隐式删除后重试。

脚本默认不构建前端；仅显式指定 `-BuildFrontend` 时运行 `npm run build`，并保留受控 `dist` 内容。它不会运行 `npm install` 或自动打开浏览器。构建前后都会拒绝 `dist` 中的重解析点；构建缺失、结构无效、包含本机绝对路径或明显凭据时，后端不会启动。

## 数据隔离

不同使用场景的规则必须区分：

- Development 默认使用 `%LOCALAPPDATA%\AIWebNovel-Development`，不得使用正式根；
- 普通无参数 integrated 启动有意允许并默认使用 `%LOCALAPPDATA%\AIWebNovel`；
- 自动测试、E2E、smoke、环境诊断写探针和正式验收运行必须显式指定或由测试框架创建唯一隔离数据根，且只能清理自己拥有的路径；
- 测试和诊断不得读取、枚举、修改、删除或重置正式 `%LOCALAPPDATA%\AIWebNovel` 的内容来证明通过；
- 自定义 `-DataRoot` 必须是安全绝对路径，不得是文件系统根，也不得经过不允许的重解析点。

正式数据保护是硬边界；允许普通 integrated 启动使用正式根不等于允许开发测试接触正式创作数据。

## 端口与停止

端口必须在合法范围内，开发模式的前后端端口不能相同。端口被占用时脚本直接失败，不随机换端口、不查询占用者命令行，也不终止占用者。

启动脚本保持前台运行。按 `Ctrl+C` 停止后，它会核对 PID 和进程启动时间，仅终止本次启动拥有的进程树，并等待端口释放。任一子进程异常退出时，另一个子进程也会被安全清理，脚本返回非零。

日志只保存在系统临时目录。异常时先完成子进程输出捕获和清理，再输出有界且脱敏的末尾诊断；清理成功后删除临时日志。仓库内不会留下 PID 文件或启动日志。输出不显示 Cookie、令牌、完整环境变量或底层命令行。

## 验收入口

```powershell
.\scripts\check_startup_runtime.ps1 -Mode Development
.\scripts\check_startup_runtime.ps1 -Mode Development -ExerciseChildFailure
.\scripts\check_startup_runtime.ps1 -Mode Integrated
.\scripts\m0_preflight.ps1
```

启动烟测必须使用专用端口和唯一隔离数据根，验证页面 ready、受控停止、端口释放和无残留进程。带 `-ExerciseChildFailure` 的 Development 场景只精确终止本次运行拥有的 Vite 监听进程，用于证明启动脚本会返回非零、清理后端同组进程并保留无关 Python 和 Node 进程。

历史 M0 预验收入口继续保留为可复现工程证据；它不重新决定 M0–M7 已冻结的正式验收结论。