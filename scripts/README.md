# 本地开发脚本

本目录包含 AIWebNovel 阶段 0 的本地质量治理脚本。所有脚本均必须从仓库根目录运行，不会创建 Git 提交、不会执行 `git add`，也不会启动开发服务器或浏览器。

## 统一质量门禁

```powershell
.\scripts\quality_gate.ps1
```

默认顺序检查 Git 差异、仓库卫生、Ruff 格式与规则、mypy、后端测试与覆盖率、Python 依赖完整性、前端质量脚本与 npm 依赖树。任一步失败都会立即返回非零退出码。默认模式不访问网络。

需要额外审计 npm 生产依赖时：

```powershell
.\scripts\quality_gate.ps1 -IncludeDependencyAudit
```

## 显式格式化

```powershell
.\scripts\format_code.ps1
```

该脚本会修改 Ruff 和 Prettier 管理的源码与测试文件，但不会修改锁文件、构建物或数据库。运行后必须人工审查 Git 差异，再重新执行统一门禁。

## 仓库卫生

```powershell
.\scripts\check_repository_hygiene.ps1
```

卫生检查只使用 `git ls-files` 得到的跟踪文件，不读取未跟踪的用户文件。它检查不应跟踪的本地产物、用户目录绝对路径和明显凭据。如发现疑似秘密，只报告仓库相对文件名和问题类型，不输出匹配值。

## 后端覆盖率检查器

`check_backend_coverage.py` 由统一门禁调用，读取写入系统临时目录的 coverage.py JSON，并分别强制语句覆盖率不低于 80%、分支覆盖率不低于 75%。门禁会在 `finally` 中删除该临时报告；检查器不会读取项目数据库或用户数据。

完整门禁、单项命令和覆盖率阈值见 [质量门禁说明](../docs/QUALITY_GATES.md)。
