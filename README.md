# AIWebNovel

AIWebNovel 是面向中文网文作者、运行于 Windows 11 本地环境的单用户 AI 长篇小说创作应用。

## 当前基线

M0 至 M7 已完成并以各自 annotated tag 冻结。当前 V1 usable foundation 已由 [M7 / V1 最终验收报告](docs/M7_ACCEPTANCE_REPORT.md)、[M7 验收清单](docs/M7_ACCEPTANCE_CHECKLIST.md)和 [M7 基线 Manifest](docs/M7_BASELINE_MANIFEST.json)正式确认。

V1 已成立的主闭环为：

`Project → Story Bible → Characters → Outline / Volumes / Chapters → Chapter Writing Workspace → Autosave → Local AI Continue / Rewrite → User explicit accept → Autosave → TXT Export`

当前仍是 Windows 本地、单用户 V1；这不表示 production SaaS、多人协作、发布平台、完整 Agent/Skill 系统或 M8+ 高级能力已经完成。M0–M7 历史标签与验收记录保持冻结，后续缺陷和演进通过新任务与新提交处理。

`docs/FEATURE_REALITY_MATRIX.md` 保留了较早阶段的细粒度能力记录，尚未完整重生成到 M7。判断当前能力时，以最新已通过里程碑的 Acceptance Report 与 Baseline Manifest 为准，不用旧矩阵否定已经正式验收的 V1 能力。

## 开发治理

仓库级开发代理规则以 [AGENTS.md](AGENTS.md) 为统一入口。重要原则：

- GitHub 当前状态是多个 ChatGPT 对话和 Codex 本地执行之间的唯一共同事实源；
- 一次只执行一个编号任务，但当前任务内部的可逆步骤不需要逐项重新确认；
- 普通开发检查失败应在授权范围内诊断、修复并重验；
- 正式验收门失败采用 hard-stop，必须经新的恢复任务后才能修改候选并重新进入正式验收；
- 正式用户数据、冻结 tag、安全边界和明确的发布/历史重写批准要求不得因为提高自主性而被放宽。

详细开发纪律见 [Codex 全局开发说明](docs/CODEX_GLOBAL_INSTRUCTIONS.md)、[开发工作流](docs/DEVELOPMENT_WORKFLOW.md)和[架构边界](docs/ARCHITECTURE_BOUNDARIES.md)。如旧阶段文档与当前明确任务冲突，按 `AGENTS.md` 的优先级解释。

## 本地运行

先从仓库根目录运行只读环境诊断：

```powershell
.\scripts\environment_doctor.ps1 -Mode Development
```

### 开发模式

```powershell
.\scripts\start_development.ps1
```

FastAPI 与 Vite 都只绑定 `127.0.0.1`。默认开发数据根为 `%LOCALAPPDATA%\AIWebNovel-Development`，与正式创作数据隔离。

### 普通本地 V1 / 集成模式

```powershell
.\scripts\start_integrated.ps1
```

默认使用已有 `frontend/dist`，FastAPI 同时提供 API 与静态前端，地址为 `http://127.0.0.1:8000`。无 `-DataRoot` 时使用正式 `%LOCALAPPDATA%\AIWebNovel`。

如果数据库文件不存在，启动流程会独占创建新数据库并迁移到当前 Alembic head；如果数据库已经存在，初始化器不会迁移、替换或重置它。只有显式传入 `-BuildFrontend` 才运行本地前端构建。

测试、E2E、smoke 和验收不得使用正式数据根，必须显式使用各自拥有的隔离 DataRoot。完整启动、数据隔离和停止规则见 [本地统一启动](docs/LOCAL_STARTUP.md)。

## 当前技术栈

- 后端：Python 3.12.10、FastAPI、Uvicorn、Pydantic、SQLAlchemy 2.x、Alembic；
- 前端：React、TypeScript、Vite；
- 数据库：SQLite，启用 WAL 和外键；
- 架构：Windows 11 本地优先、模块化单体、本地浏览器界面；
- 默认正式数据根：`%LOCALAPPDATA%\AIWebNovel`；
- 本地 AI：loopback-only OpenAI-compatible provider；不使用云 AI API 作为 V1 生产路径。

## 本地质量门禁

默认门禁：

```powershell
.\scripts\quality_gate.ps1
```

需要真实浏览器验收时：

```powershell
.\scripts\quality_gate.ps1 -IncludeE2E
```

完整门禁、依赖审计、覆盖率和 E2E 规则见 [本地质量门禁](docs/QUALITY_GATES.md) 与 [浏览器端到端测试](docs/E2E_TESTING.md)。门禁通过证明对应工程检查通过；里程碑是否正式验收通过，以对应 Acceptance Report 为准。