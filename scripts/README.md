# 脚本入口

下列脚本从仓库根目录运行。项目状态与任务顺序见 [PLAN.md](../PLAN.md)。

| 入口                                       | 用途                                                   |
| ------------------------------------------ | ------------------------------------------------------ |
| `environment_doctor.ps1 -Mode Development` | 检查开发环境并给出诊断；不会安装或修复依赖。           |
| `start_development.ps1`                    | 启动 FastAPI 与 Vite，默认使用隔离开发数据根。         |
| `start_integrated.ps1`                     | 使用已有前端构建启动集成应用；无参数时使用正式数据根。 |
| `quality_gate.ps1`                         | Default 工程门禁。                                     |
| `quality_gate.ps1 -IncludeE2E`             | Default 加完整浏览器检查。                             |
| `run_e2e.ps1 -Mode All`                    | 构建并运行全部浏览器场景，管理自有服务与临时数据。     |
| `check_e2e_cleanup.ps1`                    | 复核 E2E 自有端口、数据和成功产物的清理。              |
| `format_code.ps1`                          | 显式修改受管理源码与测试的格式；之后审查差异。         |
| `author_backup.ps1 <命令> -DataRoot <根>`  | 作者备份创建/列出/校验/恢复为新副本；必须显式给数据根。 |
| `longform_eval.ps1 -WorkRoot <根> [-Scale small\|full]` | RF-16 长篇规模评测（隔离数据+本地假模型）；默认 small 冒烟，契约结论只来自 full。 |

启动服务保持在前台，使用 `Ctrl+C` 停止；脚本核对 PID 和启动时间，只终止自己启动的进程。服务只绑定环回地址。

数据根必须区分：

- Development 默认 `%LOCALAPPDATA%\AIWebNovel-Development`。
- 普通无参数 Integrated 默认正式 `%LOCALAPPDATA%\AIWebNovel`；仅数据库文件不存在时初始化并迁移，已有数据库保持不变。
- 开发、E2E、smoke 和诊断写探针必须使用自有隔离数据根。手动用 Integrated 验证时显式传入 `-DataRoot`，不得使用作者正式根。

按任务需要查阅：

- [本地启动](../docs/LOCAL_STARTUP.md)：参数、停止行为、独立 launcher 与启动 smoke。
- [环境诊断](../docs/ENVIRONMENT_DIAGNOSTICS.md)：模式、退出码和脱敏。
- [质量门禁](../docs/QUALITY_GATES.md)：检查顺序、覆盖率与可选依赖审计。
- [E2E 说明](../docs/E2E_TESTING.md)：场景选择、浏览器准备和失败产物。
- [安全边界](../docs/SECURITY_BASELINE.md)：静态与运行时安全检查。

`m0_preflight.ps1` 保留用于历史工程流程复现，只在任务明确要求时运行；它不代表当前开发任务或重新决定已冻结验收结果。
