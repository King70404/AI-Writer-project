# 环境诊断

`scripts/environment_doctor.ps1` 是阶段0统一的非修复型环境诊断入口。它不会安装、升级或修复软件，不修改PATH、Git配置或项目代码，也不会运行完整测试。除调用者明确指定的报告文件和ENV-008隔离临时探针外，诊断不写入环境；隔离探针结束后必须清理。

## 使用方式

从仓库根目录运行：

```powershell
.\scripts\environment_doctor.ps1
.\scripts\environment_doctor.ps1 -Mode Development
.\scripts\environment_doctor.ps1 -Mode Integrated
.\scripts\environment_doctor.ps1 -Mode M0
.\scripts\environment_doctor.ps1 -Json
$reportPath = Join-Path ([System.IO.Path]::GetTempPath()) "AIWebNovel-doctor.json"
.\scripts\environment_doctor.ps1 -OutputFile $reportPath
```

默认模式为`Development`。`-OutputFile`只写入调用者明确指定的文件；父目录必须已经存在。仓库内输出只允许放入已经存在且被忽略的`.runtime`目录，推荐使用上例的系统临时目录。JSON文件使用UTF-8编码。

## 检查模型

每个检查都包含稳定的`check_id`、名称、状态、安全摘要、结构化详情、修复建议、是否必需以及实际耗时。检查顺序固定为：

| ID | 检查 |
| --- | --- |
| ENV-001 | Windows操作系统摘要 |
| ENV-002 | Git可用性、分支和工作区状态 |
| ENV-003 | Python 3.12.10 x64、pip和venv |
| ENV-004 | 仓库`.venv`、后端导入和`pip check` |
| ENV-005 | Node.js 24 x64、npm和前端依赖 |
| ENV-006 | Playwright与Chromium |
| ENV-007 | 后端配置和安全基线 |
| ENV-008 | 正式根存在性与隔离存储/数据库探针 |
| ENV-009 | 指定环回端口可绑定性 |
| ENV-010 | 前端生产构建完整性 |
| ENV-011 | 本地质量工具入口 |
| ENV-012 | Git已跟踪内容的仓库卫生 |

单项状态只可能是`pass`、`warning`、`fail`或`skipped`。任一必需检查失败或被跳过时，总状态为`not_ready`；没有必需失败但存在警告时为`ready_with_warnings`；其余为`ready`。

退出码固定为：

| 退出码 | 含义 |
| --- | --- |
| 0 | `ready` |
| 1 | `ready_with_warnings` |
| 2 | `not_ready` |
| 3 | 参数或输出目标错误 |

## 模式差异

- `Development`允许Git工作区不干净、Playwright缺失、生产构建缺失或端口占用成为警告。
- `Integrated`要求生产构建和指定端口可用；Git不干净仍是警告。
- `M0`要求Git工作区干净、Chromium、构建、质量工具、存储和数据库探针全部通过，不接受必需警告。

## 数据与脱敏边界

诊断只判断正式`%LOCALAPPDATA%\AIWebNovel`是否存在，不枚举、不读取内容，也不会创建该目录。写入探针只在独立的`AIWebNovel-Doctor-<随机标识>`临时根中执行，并在结束后清理。

文本与JSON使用同一套脱敏规则，路径显示为`<repo>`、`<venv>`、`<localappdata>`或`<temp-data-root>`。用户名、Cookie、CSRF、Authorization、密码、令牌、私钥、环境变量原值以及外部命令的原始错误输出不会写入报告。`-Verbose`也不解除这些限制。

## 与质量门禁和M0验收的关系

普通诊断默认不联网，也不运行Ruff、pytest、Vitest或E2E，只确认相应入口存在。完整门禁仍由`scripts/quality_gate.ps1`执行。

`scripts/m0_preflight.ps1`会组合严格诊断、质量门禁、真实启动烟测、存储和安全烟测并生成预验收证据。预验收通过不等于M0正式阶段验收通过。
