# 前端开发

`src/` 保存 React 界面与 API 客户端，前端用例位于 `../tests/frontend/`，浏览器用例位于 `../tests/e2e/`。当前项目状态见 [PLAN.md](../PLAN.md)。

使用 64 位 Node.js 24 和随附 npm。在本目录执行：

```powershell
npm ci
npm run test:run
npm run quality
```

`quality` 依次运行格式检查、ESLint、TypeScript、覆盖率测试和生产构建；`npm run build` 单独执行类型检查与构建。开发页面应从仓库根目录通过 `scripts/start_development.ps1` 启动，以同时启动真实后端并正确配置 Vite 代理。

浏览器验收按需执行：

```powershell
npm run e2e:install
npm run e2e
```

首次缺少项目管理的 Chromium 时才需要 `e2e:install`。`e2e` 使用真实服务及独立临时数据，包含开发、集成和缺失构建场景；具体单项入口、失败产物和清理规则见 [E2E 说明](../docs/E2E_TESTING.md)。

Development 默认数据根为 `%LOCALAPPDATA%\AIWebNovel-Development`；普通无参数集成启动使用正式 `%LOCALAPPDATA%\AIWebNovel`，不能作为测试数据根。详情见 [本地启动](../docs/LOCAL_STARTUP.md)。

前端始终通过相对 `/api/v1` 调用本地后端，不把 CSRF、ETag 或未提交草稿写入浏览器持久存储。API 响应解析、作者确认及并发处理不能因界面调整而被绕过。完整工程检查见 [质量门禁](../docs/QUALITY_GATES.md)。
