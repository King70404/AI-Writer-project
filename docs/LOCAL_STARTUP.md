# 本地统一启动

阶段0提供开发模式和生产集成模式两个前台启动入口。它们只用于工程开发和验收，不代表小说业务功能已经实现。

## 开发模式

```powershell
.\scripts\start_development.ps1
.\scripts\start_development.ps1 -BackendPort 8001 -FrontendPort 5174
.\scripts\start_development.ps1 -DataRoot <绝对开发数据根>
```

默认行为：

- FastAPI绑定`127.0.0.1:8000`；
- Vite绑定`127.0.0.1:5173`；
- Vite代理指向本次指定的后端端口；
- 数据根为`%LOCALAPPDATA%\AIWebNovel-Development`；
- 启动前执行`Development`模式环境诊断。

`-NoPreflight`只跳过普通诊断，Python、Node、端口和数据根安全检查仍会执行。脚本不会安装依赖、构建前端、运行Alembic迁移或自动打开浏览器。

## 集成模式

```powershell
.\scripts\start_integrated.ps1
.\scripts\start_integrated.ps1 -Port 8001
.\scripts\start_integrated.ps1 -BuildFrontend
.\scripts\start_integrated.ps1 -DataRoot <绝对集成开发数据根>
```

默认只启动FastAPI，由其提供已有的`frontend/dist`，绑定`127.0.0.1:8000`，使用`%LOCALAPPDATA%\AIWebNovel-Integrated-Development`。运行环境固定为production，API文档默认关闭。

脚本默认不构建；仅显式指定`-BuildFrontend`时运行`npm run build`，并向Vite传递`--emptyOutDir false`以保留已有`dist`内容。它不会运行`npm install`、执行迁移或自动打开浏览器。构建前后都会递归拒绝`dist`中的重解析点；构建缺失、结构无效、包含本机绝对路径或明显凭据时，后端不会启动。

## 数据隔离

两个入口都拒绝正式`%LOCALAPPDATA%\AIWebNovel`及其父子重叠路径。自定义`-DataRoot`必须是绝对路径、不得是文件系统根、不得经过重解析点。开发模式和集成模式使用不同的默认开发数据根。

## 端口与停止

端口必须在合法范围内，开发模式的前后端端口不能相同。端口被占用时脚本直接失败，不随机换端口、不查询占用者命令行，也不终止占用者。

启动脚本保持前台运行。按`Ctrl+C`停止后，它会核对PID和进程启动时间，仅终止本次启动拥有的进程树，并等待端口释放。任一子进程异常退出时，另一个子进程也会被安全清理，脚本返回非零。

日志只保存在系统临时目录。异常时先完成子进程输出捕获和清理，再输出有界且脱敏的末尾诊断；清理成功后删除临时日志。仓库内不会留下PID文件或启动日志。输出不显示Cookie、令牌、完整环境变量或底层命令行。

## 验收入口

```powershell
.\scripts\check_startup_runtime.ps1 -Mode Development
.\scripts\check_startup_runtime.ps1 -Mode Development -ExerciseChildFailure
.\scripts\check_startup_runtime.ps1 -Mode Integrated
.\scripts\m0_preflight.ps1
```

启动烟测使用专用端口和唯一隔离数据根，验证页面ready、受控停止、端口释放和无残留进程。带`-ExerciseChildFailure`的Development场景只精确终止本次运行拥有的Vite监听进程，用于证明启动脚本会返回非零、清理后端同组进程并保留无关Python和Node进程。M0预验收只生成阶段验收准备证据，不宣告M0正式完成。

Windows安装器、Windows服务、自动更新、系统托盘和正式创作模式属于后续阶段，本任务不提供这些能力。
