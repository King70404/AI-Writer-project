# AIWebNovel 前端

本目录包含 AIWebNovel 的 React、TypeScript 与 Vite 前端工程基础。

## 当前范围

当前只有阶段 0 工程基础页、最小路由、全局错误边界和未被业务页面调用的类型化 API 客户端基础。前端尚未连接后端，也没有小说项目、规划、写作或评审等业务功能。前后端集成将在 DEV-0.5 中建立。

## 环境要求

- 正式 64 位 Node.js `>=24.0.0 <25.0.0`；
- npm，使用随 Node.js 提供的版本。

## 本地命令

以下命令均从本目录执行：

```powershell
npm install
npm run dev
npm run typecheck
npm run test:run
npm run test
npm run build
npm run preview
```

`npm run dev` 默认仅绑定 `127.0.0.1:5173`。`npm run test` 进入交互测试模式，`npm run test:run` 单次运行全部前端测试。`npm run build` 先执行严格类型检查，再将本地生产构建写入被 Git 忽略的 `dist/`；`npm run preview` 仅用于本地查看该构建。
