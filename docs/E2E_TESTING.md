# 浏览器端到端测试

Playwright在独立本地数据根上验收开发与生产集成服务。`E2E-INT-006`至`E2E-INT-010`覆盖Project API、稳定Keyset列表、前端创建/修订/显式412恢复和不可变Revision历史；`E2E-INT-011`至`E2E-INT-013`覆盖Story Bible HTTP、前端当前流程与只读历史；`E2E-INT-014`至`E2E-INT-016`覆盖Character HTTP、前端创建/稳定列表/当前修订/显式412恢复及只读历史。这十一个业务场景只对自己的临时数据库显式迁移；应用启动本身仍不迁移。

## 安装

Playwright 是 `frontend` 的本地开发依赖，版本由 `package-lock.json` 固定。项目只安装 Playwright 管理的 Chromium，以控制下载量和测试矩阵；本阶段不安装 Firefox、WebKit，也不读取系统 Chrome、Edge 或用户浏览器配置。

首次运行或本地浏览器缓存缺失时，在 `frontend` 目录执行：

```powershell
npm run e2e:install
npx playwright install --list
```

Chromium 二进制由 Playwright 保存在当前用户的仓库外缓存中，不进入 Git。默认 E2E 命令不会自动下载浏览器；缺失时会失败并提示上述安装命令。

## 运行命令

在 `frontend` 目录执行：

```powershell
npm run e2e:dev
npm run e2e:integrated
npm run e2e
```

- `e2e:dev` 验证 Vite 页面、真实健康检查、手动重新检查和客户端路由；
- `e2e:integrated`先构建前端，再验证FastAPI静态服务、生产安全基线、Project API/前端/历史、Story Bible HTTP/前端/历史、Character HTTP/前端链路，以及缺失构建的安全失败；
- `e2e` 按开发模式、生产集成模式的顺序运行全部浏览器验收，任一阶段失败即返回非零。

每个场景都重新启动所需服务并使用独立 `AIWEBNOVEL_DATA_ROOT`，不依赖其他场景的执行顺序。需要独立复现单项时，在对应模式后传入固定场景编号，例如：

```powershell
npm run e2e:dev -- -Scenario E2E-DEV-001
npm run e2e:integrated -- -Scenario E2E-INT-003
npm run e2e:integrated -- -Scenario E2E-INT-005
npm run e2e:integrated -- -Scenario E2E-INT-006
npm run e2e:integrated -- -Scenario E2E-INT-007
npm run e2e:integrated -- -Scenario E2E-INT-008
npm run e2e:integrated -- -Scenario E2E-INT-009
npm run e2e:integrated -- -Scenario E2E-INT-010
npm run e2e:integrated -- -Scenario E2E-INT-011
npm run e2e:integrated -- -Scenario E2E-INT-012
npm run e2e:integrated -- -Scenario E2E-INT-016
```

当前完整集共31个场景：3个开发模式、27个生产集成模式和1个缺失构建启动失败场景。`E2E-INT-014`验证Character HTTP创建、稳定列表与并发修订；`E2E-INT-015`验证Character当前前端流程；`E2E-INT-016`在生产构建、真实后端和临时0004 SQLite上验证历史入口与直接刷新、首屏一个列表GET且无详情GET、21个Revision的20+1分页、Head current、按需profile、快速切换取消、无历史写入、隐私及数据库/资源清理。

`E2E-INT-021` 使用自有隔离小说和真实受控 HTTP 模型服务，验证跨章伤势事实提取、作者确认、前文召回、一致性评审、准备定向改写、作者采用，以及前文修改后的事实失效与章节复核入口。准备和刷新不调用模型；测试不使用真实付费模型或作者数据。

`E2E-INT-022` 在生产构建和自有隔离数据根上创建小说，经“备份与恢复”页面立即备份、校验完整性、下载 ZIP，再恢复到运行目录内的新副本文件夹 `e2e-restored-copy` 并核对计数；同名非空目标的第二次恢复必须被 409 拒绝。测试不读取或恢复作者正式数据与正式备份。

`E2E-INT-023` 验证 A1 作者工作台：无本机记录的首页不显示继续写作或统计数字；经书架新建小说、卷与两章后进入三栏写作台，核对卷章导航当前章、固定状态区、三栏不重叠及无横向溢出；未保存正文切章前先保存；专注模式收起两侧栏、`Escape` 退出且编辑器内容保留；在“生成”分区原地添加本机模型并自动选中；在“准备”分区确认规则版本、“将此规则加入本章规划”、保存规划后回到“生成”；最后从首页“继续写作”和书架进入最近章节。全程断言无生成/分析/评审请求，本机存储只含章节定位标识。

`E2E-INT-024` 验证 A2 工作台汇总：新建小说后结构页“写作进度与待处理”显示 0 字、0 章 / 0 卷与无待办；建卷与两章后汇总随之刷新为 2 章 / 1 卷、全部草稿；写入含空格、制表符、换行和全角空格的正文并保存，作者把章节标为“待检查”后，汇总字数等于非空白字符数，按需展开的分页章表核对各章字数与状态；标为“定稿”后再改正文，状态区显示“标记后正文已修改”，首页紧凑汇总出现“定稿后正文已修改”1 项待办并可跳回该章，“按当前正文重新标记”后待办清空、刷新后状态不变。断言汇总与状态响应不含正文、全程无生成/分析/评审请求、浏览器审计干净（两次进入结构页读取尚未创建的大纲各声明一次精确的 404）。

`E2E-INT-025` 验证 B1 候选对照与本章模型用量：使用与 `E2E-INT-021` 相同的 `127.0.0.1:18123` 受控 HTTP 模型服务和 AI 环境，经 API 建小说、卷、章与正文，在“生成”分区原地添加指向该服务的本机模型（不存储密钥，Linux 无 DPAPI 也可运行）。打开“本章模型用量”先显示无记录且不调用模型；续写候选显示“候选插入位置”（正文末尾与候选），改写候选显示“原文与候选对照”，原文栏等于任务准备时保存的选区、候选栏等于候选，可切换“只看原文/只看候选/对照”。假模型第一次响应带 OpenAI 兼容 `usage`（321/123/444），第二次省略 `usage`：已打开的面板在生成后自动重读，分别显示“服务商报告：输入 321 · 输出 123 token”和“用量未知（服务商未报告）”，合计只计已报告值、未知 1 次不按 0 计，`GET /projects/{id}/usage` 与界面一致。刷新后候选仍待确认，编辑器与服务器正文均未被自动采用；查看与刷新用量不产生额外模型请求，浏览器审计干净。

`E2E-INT-026` 验证 B2 候选编辑与发送前预算：同样使用 `127.0.0.1:18123` 受控模型服务与 AI 环境，在 UI 中添加本机模型（不存储密钥）。先在“费用与预算”为当前模型填写价格（CNY，每百万 token 输入/输出 1000，不预置），预算保持“不设预算”；续写前可见“发送前预估（保守上限，不是账单）”，发送得到候选。编辑候选并“保存修改”后只生成作者修改第 1 版：候选原文、编辑器与服务器正文都不变，未保存时不能采用；点击“追加修改后的文本”后正文追加作者版本，不含原始候选，“已处理候选”显示“已采纳（采用作者修改版本）”且保留原始模型文本。随后设严格预算（单任务上限 0.01 CNY）：预估显示“按严格预算不会发送”，发送按钮禁用，直接调用 generate 返回 409 `AI_BUDGET_REFUSED`，假模型请求数与用量台账次数都不增加。改为提示模式后预估显示“预算提示”，必须勾选“我已知晓可能超出预算，仍要发送这一次”才可发送，发送后请求与台账各加 1；浏览器审计干净。

`E2E-INT-027` 验证 C 长篇规划与召回：不需要 AI 环境，经 API 建本机模型档案并断言受控模型服务收到 0 次请求；在结构页建立全书/卷目标、带原文证据的伏笔线、故事事件与人物状态，时间线显示到期伏笔；在写作页固定一条事实并排除一条后准备任务，冻结的来源包含作者规划与固定事实、不含排除事实；浏览器审计干净（结构页读取尚未创建的大纲预期 404）。

V1-UX-1-R4 在 `E2E-INT-016` 原有只读历史断言之后增加小说删除回归：通过精确书名确认删除同一个临时小说，已打开历史页再请求未读正文及重新打开旧历史链接均须返回 404 且不显示档案。数据库验后检查保留全部 21 条角色修订与原小说修订，并验证仅追加预期的小说删除标记。设定/角色普通页面的内部 ID 与并发信息隐藏也纳入受影响 E2E；API/ETag、历史版本、冲突和浏览器审计断言继续保留。

统一启动入口的最低浏览器验收由仓库根目录的受控脚本执行：

```powershell
.\scripts\check_startup_runtime.ps1 -Mode Development
.\scripts\check_startup_runtime.ps1 -Mode Integrated
```

Development与Integrated烟测使用专用临时端口和唯一隔离数据根；它们不会复制全部26个E2E场景。`E2E-INT-006`至`E2E-INT-010`保留Project API、稳定列表、前端创建/修订与不可变历史证据；`E2E-INT-011`至`E2E-INT-013`验证Story Bible HTTP、真实前端当前流程和只读历史；`E2E-INT-014/015`验证Character HTTP与当前前端流程；`E2E-INT-016`验证Character只读Revision历史、取消竞态、21个不可变Revision与完整清理。

默认使用无头 Chromium、`retries=0` 和单 worker，不自动打开报告或浏览器窗口。人工调试时可执行 `npm run e2e:headed`；失败后执行 `npm run e2e:report` 查看本地 HTML 报告。截图和 trace 只在失败时保留，视频关闭；成功运行会删除无用的模式报告和结果目录。

## 本地服务与临时数据

E2E 使用固定专用 loopback 端口，启动前必须确认端口空闲，绝不复用开发者已经启动的服务：

| 模式             | 服务    |  端口 |
| ---------------- | ------- | ----: |
| 开发             | Vite    | 14173 |
| 开发             | FastAPI | 18120 |
| 生产集成         | FastAPI | 18121 |
| 缺失构建失败验收 | FastAPI | 18122 |

开发模式只从 Vite 访问页面，Vite 的 `/api` 代理仅指向本次 E2E 后端，并为测试关闭 HMR WebSocket。生产集成模式不启动 Vite；正常构建验收结束并清理后，才以缺少 `index.html` 的受控目录启动独立失败验收进程。

每个独立场景创建带 E2E 标识和随机值的唯一临时数据根，并通过子进程环境变量传入。应用数据库只能位于该根的 `data/aiwebnovel.sqlite3`，应用运行目录只能位于该根的 `runtime/`；它不使用正式 `%LOCALAPPDATA%\AIWebNovel`，也不读取该目录。场景可以另用受控编排目录保存 PID 清单和短期诊断，但编排目录不是应用数据根。

运行结束会清理数据库及 WAL、SHM、journal、整个场景数据根、临时构建目录和服务诊断。清理只接受本场景记录、位于受控父目录内且名称带 E2E 标识的精确路径；不会按模糊名称删除，也不会影响其他测试进程。`run_e2e.ps1` 保存启动器及其实际 Node/Python 服务的 PID 与启动时间，只终止本次记录的进程树，不按进程名结束其他 Node 或 Python 进程；清理失败会使测试失败，`check_e2e_cleanup.ps1` 复核专用端口、编排目录和成功运行产物均已释放。

所有正常开发和生产集成场景的 ready 响应必须包含真实的 `storage=ok` 与 `database=ok`。缺失构建场景只允许 `frontend=failed`，不能以存储失败掩盖预期的前端故障。

DEV-0.9 起，正常场景的 ready 还必须包含 `security=ok`。生产集成验收同时证明：HTML 与 API 基础安全头存在、CSP 不阻止本地 React 构建、Uvicorn 不公开 Server 版本、生产 `/docs`、`/redoc` 与 `/openapi.json` 关闭、非法 Host 被拒绝、session 接口设置 HttpOnly/SameSite Cookie，且浏览器 `localStorage` 与 `sessionStorage` 中没有 CSRF 令牌。测试和诊断不得打印 Cookie 或 CSRF 原值。

## 安全隔离与诊断

每个浏览器上下文安装网络守卫，只允许当前模式的 `http://127.0.0.1:<端口>`，同时阻止外部 HTTP、WebSocket 和 `file://`。页面错误、非预期控制台错误和非预期请求失败会使测试失败；受控竞态场景可按精确本地路径声明一次预期Abort，其他失败仍阻断。诊断只记录主机与路径摘要，不记录查询参数、Cookie、Authorization、CSRF 令牌或完整页面 HTML。伪造代理头不能改变 Host、scheme、客户端来源或同源判断；服务启动器显式保持代理头不受信任。

失败产物只保存在被 Git 忽略的 `frontend/playwright-results/` 与 `frontend/playwright-report/`。服务启动错误只输出经过路径替换、行数和长度限制的日志尾部；无论成功、断言失败或受控启动中断，服务和临时数据库清理都在 `finally` 中执行。

## 统一质量门禁

浏览器 E2E 需要额外的 Chromium 缓存、真实服务进程和较长运行时间，因此不属于默认离线质量门禁。默认门禁仍执行：

```powershell
.\scripts\quality_gate.ps1
```

需要完整浏览器验收时显式执行：

```powershell
.\scripts\quality_gate.ps1 -IncludeE2E
.\scripts\quality_gate.ps1 -IncludeDependencyAudit -IncludeE2E
```

`-IncludeE2E` 只在既有门禁及可选审计通过后运行 E2E，并在成功后执行清理复核。它不会安装浏览器、修改源码、创建提交或访问外部网页。
