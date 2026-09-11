# AIWebNovel repository agent instructions

本文件适用于整个仓库，是开发代理执行任务时的统一控制入口。它不替代产品运行时的作者确认、安全边界或里程碑验收事实。

## 1. 共同事实源与规则优先级

GitHub 当前仓库状态是多个 ChatGPT 对话、Codex 本地执行和审阅之间的唯一共同事实源。开始任务前先确认 GitHub 最新状态；本地未提交或未同步的状态不能被其他线程视为共同事实。

发生指令冲突时，按以下顺序解释：

1. 当前明确批准的 GitHub Issue、任务说明、PR 验收计划或恢复任务；
2. 本 `AGENTS.md`；
3. 最新已通过里程碑的 Acceptance Report 与 Baseline Manifest；
4. 当前操作文档，例如 `QUALITY_GATES.md`、`LOCAL_STARTUP.md`、`E2E_TESTING.md`、`ENVIRONMENT_DIAGNOSTICS.md`；
5. 当前架构、领域和 API 契约文档；
6. `README.md`、`FEATURE_REALITY_MATRIX.md` 等说明性汇总；
7. 已完成的旧 DEV 任务说明和旧里程碑文档，仅作为当时范围与历史证据。

较低优先级文档不得缩小较高优先级任务已经明确授权的范围。旧 DEV 文档中的“下一任务需独立授权”等措辞，在对应任务已经完成后只记录历史边界，不会对新的、已明确批准的任务制造第二次批准要求。

如果冲突能由上述优先级唯一解决，应继续执行并在报告中记录解释。只有无法唯一解决，而且不同解释会实质改变产品范围、安全边界、不可逆操作、正式用户数据或验收标准时，才停止并请求澄清。

`docs/FEATURE_REALITY_MATRIX.md` 是当前能力索引；M0–M2 时期的旧细粒度矩阵已归档到 `docs/history/FEATURE_REALITY_MATRIX_PRE_M7.md`。若说明性矩阵与最新已通过里程碑冲突，仍以最新 Acceptance Report 与 Baseline Manifest 为当前能力事实。

## 2. 当前任务内的自主性

一次只执行一个编号任务，限制的是跨任务扩展，不是把一个任务拆成需要逐步确认的多个停点。

在当前任务已经明确授权的范围、文件和模块内，执行者应自主完成全部可逆步骤，包括：

- 读取需要的仓库文件和当前 Git 状态；
- 修改允许范围内的文件；
- 运行格式、lint、类型检查、单元测试、集成测试和任务要求的其他检查；
- 诊断失败原因；
- 在当前授权范围内修复失败并重新运行开发检查；
- 更新与该任务直接相关的文档和验收证据；
- 输出完整的完成或未完成报告。

这些步骤不需要逐项再次请求批准。不得因为已经完成“修改代码”而在测试、诊断或任务内修复之前无故停止。

## 3. 开发模式与正式验收模式

### Development mode

普通开发或修复任务中，测试或检查失败是任务内反馈。只要修复仍处于当前批准的范围内，应诊断、修复并重新运行适用检查；在完成定义满足之前不得开始下一个编号任务。

### Formal acceptance mode

正式里程碑、正式恢复门禁或明确标记为 formal acceptance 的任务采用 hard-stop：规定的正式门一旦失败，立即保留失败证据并停止该次正式验收；不得在同一验收任务中修改候选、降低阈值、增加规避性 sleep/retry、跳过测试或擅自重跑失败的正式门。必须由新的、明确的恢复任务授权后才能修改候选并再次进入正式验收。

预验收、普通单测或开发期质量检查不应被误当成 formal acceptance，除非当前任务明确这样规定。

## 4. 必须保留的明确批准与安全边界

以下事项不会因为本文件提高任务内自主性而获得默认授权：

- 开始新的编号任务或扩大当前业务/架构范围；
- force push、破坏性 reset、历史重写、移动或重建冻结 tag；
- 未由当前任务明确授权的 push、merge、release 或其他持久外部发布动作；
- 删除、重置、覆盖、迁移或读取作者正式创作数据和正式备份以用于开发/测试；
- 放宽 Host、CORS、CSRF、数据隔离、安全门或质量阈值来取得通过；
- 删除、弱化或跳过已有测试来声明完成；
- 处理或暴露密码、Cookie、令牌、私钥等秘密；
- 产品运行时把 AI 候选、候选事实或候选风格规则提交为正式内容所需的作者确认。

M0–M7 冻结标签与验收历史保持不可移动、不可覆盖、不可改写；发现缺陷必须通过新任务、新提交和新的恢复/演进记录处理。

## 5. 数据根与启动规则

- Development 默认数据根为 `%LOCALAPPDATA%\AIWebNovel-Development`，不得使用正式 `%LOCALAPPDATA%\AIWebNovel`。
- `start_integrated.ps1` 无 `-DataRoot` 时的当前产品行为是使用正式 `%LOCALAPPDATA%\AIWebNovel`；这是普通本地 V1 集成启动路径，不是自动测试数据根。
- 自动测试、E2E、smoke、诊断写探针和正式验收运行必须显式使用各自拥有的隔离数据根，并只清理自己创建的路径。
- 任何测试或诊断不得通过读取、枚举、修改、删除或重置正式数据根来证明通过。

具体行为以当前脚本和 `docs/LOCAL_STARTUP.md` 为准。

## 6. 开发代理与产品运行时 AI 的作用域

`docs/CODEX_GLOBAL_INSTRUCTIONS.md` 同时记录产品运行时 AI/CodexExecutor 的安全模型和开发纪律。创作模式中的沙箱、作者确认、候选区、Canon P0-P4 等规则约束 AIWebNovel 运行后的产品行为；除非明确标注为开发规则，不得把这些运行时限制解释成禁止开发代理执行当前已批准的仓库任务。

反之，开发代理的仓库修改权限也不赋予产品运行时模型 P4、正式事实提交权或跳过作者确认的能力。

## 7. 完成与报告

执行者必须以当前任务的完成定义为终点，而不是以某个中间步骤为终点。无法满足完成定义时，明确列出失败项、已完成证据、未完成原因和下一恢复入口，不伪造完成。

重要需求、方向、架构决策、代码变化、验收结果和最终任务状态必须最终同步到 Git/GitHub，供其他工作线程复用。

## 8. 跨对话项目接力与 `PLAN.md`

根目录 `PLAN.md` 是跨 ChatGPT 对话、Codex 本地执行与 GitHub 审阅之间的当前项目接力页，专门回答：之前做了什么、现在是什么状态、卡在哪里、下一步做什么。

每次开始仓库任务时，按以下顺序读取并确认：

1. GitHub 当前 `main`、相关分支、Issue 与 PR；
2. 根目录 `AGENTS.md`；
3. 根目录 `PLAN.md`；
4. 当前编号任务的 Issue / PR / formal acceptance 或 recovery 记录；
5. 该任务需要的模块、架构与操作文档。

`PLAN.md` 是状态接力页，不替代 Issue、PR、Acceptance Report 或 Baseline Manifest 的证据效力。若它与更高优先级的 GitHub 事实冲突，以第 1 节优先级为准，并在当前协调或任务收尾中同步修正 `PLAN.md`。

以下事件发生后必须同步 `PLAN.md`：

- 新编号任务开始、完成、取消或被恢复任务阻塞；
- PR 创建、候选 SHA 改变、合并或关闭；
- formal acceptance PASS / FAIL；
- 发现新的真实 blocker 或创建 recovery task；
- 正式基线、当前阶段或下一任务顺序改变；
- 用户批准新的重要产品/架构方向。

`PLAN.md` 至少应保持这些区块可读：当前阶段、已完成的重要历史、当前活动工作、当前 blocker / recovery、下一步顺序、当前禁止事项。它应保持简洁并链接到精确 Issue / PR，而不是复制全部验收日志。

正式验收一旦失败，必须把 FAIL、首个真实 blocker 和“下一步必须是新的 recovery task”同步到 GitHub 与 `PLAN.md`；不得在同一 formal acceptance 任务中悄悄修改候选后重跑。

不得在 `PLAN.md`、`AGENTS.md` 或其他协调文档中写入 API Key、密码、Cookie、令牌、私钥、作者正式创作内容或其他秘密/正式用户数据。

## 9. Green Candidate / formal acceptance 入口条件

完整规则见 `docs/ACCEPTANCE_STABILITY.md`。

新的 formal acceptance 不得成为候选第一次运行完整门禁的地方。创建 formal acceptance Issue 前，精确 candidate SHA 必须先完成 Development / RC preflight：

1. Default quality gate PASS；
2. 同一未修改 SHA 的 `quality_gate.ps1 -IncludeE2E` 连续 PASS 两次；
3. 当前任务要求的 Windows launcher smoke PASS；
4. 当前任务要求的隔离真实作者 smoke PASS；
5. 已知 timing/flaky 测试完成专门重复稳定性验证；
6. 前端/浏览器测试没有未解释的 React warning、console error、pageerror 或 requestfailed；
7. Git、migration、tag、frozen-history 与正式用户数据边界全部满足任务要求。

candidate 在 preflight 期间有任何新 commit，连续绿色计数清零，必须从新 SHA 重新开始。

不得用 timeout inflation、sleep、retry、skip、删除测试、降低 coverage 或弱化断言来满足 Green Candidate 条件。

发生晚期失败时，除了修复当前 blocker，还必须把能前移的检查补到 Development / CI / RC preflight，避免同类问题下一次仍然只在 formal acceptance 才被发现。

开始最终 RC preflight 前，应先同步 `PLAN.md` 与活动 Issue/PR，然后冻结 candidate。冻结期间不要仅为了协调状态而向 `main` 追加 commit；动态状态写入当前 Issue/PR，待 candidate 最终 PASS/FAIL 后再同步 `PLAN.md`。