# 开发工作流

本文件描述当前开发任务的执行方式。仓库级优先级、自主性、批准和停止规则以根目录 [`AGENTS.md`](../AGENTS.md) 为准；M0–M7 期间逐个 DEV 任务的原始授权边界已原样保存在 [`history/DEVELOPMENT_WORKFLOW_M0_M7.md`](history/DEVELOPMENT_WORKFLOW_M0_M7.md)，仅作为历史证据，不对新的明确任务制造二次批准要求。

## 任务纪律

1. 一次只执行一个编号任务，不并行扩展其他编号任务的能力。
2. 当前任务必须有明确范围、禁止范围、依赖、检查方法和完成定义。
3. “一次一个任务”限制跨任务扩展，不限制当前任务内部连续完成读取、修改、格式化、测试、诊断、范围内修复和开发检查重跑。
4. 不允许使用 TODO、假数据、空页面、空按钮、假进度或无真实后端行为的展示声明完成。
5. 不得删除、弱化或跳过已有测试来取得通过。
6. 当前任务未满足完成定义时不得开始下一编号任务。
7. 报告必须准确区分完成、未完成和不适用项。

## Development mode

普通开发或修复任务中，测试或检查失败属于任务内反馈。只要修复仍在当前批准的范围内，应继续诊断、修复并重新运行适用检查；不需要因为每一次失败或每一个子步骤重新请求批准。

如果问题只能通过扩大业务范围、改变架构边界、接触正式用户数据、降低安全/质量门或执行其他未授权动作解决，则停止并报告需要的新授权。

## Formal acceptance mode

正式里程碑、正式恢复门禁或当前任务明确标记为 formal acceptance 时采用 hard-stop：规定的正式门一旦失败，保留失败证据并停止该次正式验收；不得在同一验收任务中修改候选、降低门槛、增加规避性 sleep/retry、跳过测试或擅自重跑失败的正式门。

进入修复必须由新的明确恢复任务授权；修复完成后，再按新任务规定重新进入正式验收。

预验收、普通单测和开发期质量检查不自动获得 formal acceptance 的 hard-stop 语义。

## 规格冲突与澄清

先按 `AGENTS.md` 的规则优先级解决冲突。能被更高优先级来源唯一解决的冲突应继续执行并在报告中记录。

只有当冲突无法唯一解决，而且不同解释会实质改变以下任一事项时才停止并请求澄清：

- 产品或架构范围；
- 安全边界；
- 不可逆操作；
- 正式用户数据；
- 正式验收标准。

明显过时的 README、旧 DEV 任务限制或历史能力矩阵，不应覆盖当前明确任务和最新已通过里程碑事实。

## 数据隔离

作者正式默认数据根是 `%LOCALAPPDATA%\AIWebNovel`。

- Development 默认使用 `%LOCALAPPDATA%\AIWebNovel-Development`，不得使用正式根；
- 普通无参数 `start_integrated.ps1` 当前有意使用正式 `%LOCALAPPDATA%\AIWebNovel`，这是本地 V1 普通启动路径；
- 自动测试、E2E、smoke、诊断写探针和验收运行必须显式使用各自拥有的隔离数据根；
- 开发和测试不得读取、枚举、修改、删除或重置作者正式创作项目或正式备份；
- 测试结束只清理测试自己拥有的数据库、WAL、SHM、journal、运行目录和临时根。

完整启动边界见 [`LOCAL_STARTUP.md`](LOCAL_STARTUP.md)，存储边界见 [`LOCAL_STORAGE.md`](LOCAL_STORAGE.md)。

## 安全开发纪律

- 本地服务保持 loopback 绑定，不得为了调试改为 LAN 或公网监听；
- 不得通过通配符放宽 Host/CORS，也不得绕过 Origin、Session、CSRF 等既有安全边界；
- 不得记录请求正文、Cookie、Authorization、会话 ID、CSRF 令牌、完整查询字符串或其他秘密；
- 安全门失败不得通过放宽策略、降低阈值或跳过门禁继续；
- 正式用户数据保护、冻结标签和历史验收事实不因任务内自主性提高而放宽。

完整安全边界见 [`SECURITY_BASELINE.md`](SECURITY_BASELINE.md)。

## 质量门

默认工程门禁从仓库根目录运行：

```powershell
.\scripts\quality_gate.ps1
```

需要真实浏览器验收时：

```powershell
.\scripts\quality_gate.ps1 -IncludeE2E
```

只有任务明确要求联网生产依赖审计时才运行 `-IncludeDependencyAudit`。完整命令、覆盖率和失败行为见 [`QUALITY_GATES.md`](QUALITY_GATES.md) 与 [`E2E_TESTING.md`](E2E_TESTING.md)。

Development mode 下门禁失败可在当前范围内修复后重验；Formal acceptance mode 下正式门失败遵守 hard-stop。

## 冻结历史

M0–M7 已通过的 annotated tags、Acceptance Reports、Acceptance Checklists 与 Baseline Manifests 是历史冻结证据。不得移动、覆盖、重建标签或改写当时的验收事实。后续缺陷和演进必须通过新的编号任务与新提交处理。

旧阶段文档仍可用于理解当时为什么禁止某项能力，但它们不自动限制一个新的、更高优先级任务已经明确授权的范围。