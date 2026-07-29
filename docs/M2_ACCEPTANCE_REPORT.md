# M2 Story Bible基础能力正式验收报告

## 1. 正式验收结论

DEV-2.1至DEV-2.6形成的Story Bible基础闭环已按DEV-2.7重新执行可复现验收，全部阻断门禁通过，可以冻结为M2历史基线。

## 2. 验收时间

- aware UTC：`2026-07-28T15:03:33.679Z`
- 本地时区（Asia/Shanghai，UTC+08:00）：`2026-07-28T23:03:33.679+08:00`

## 3. 验收源实现

- 实现提交：`2e28d41a304a80ad9544dfea7558ae4c05563ca1`
- 提交信息：`feat(story-bible): add immutable revision history`
- 验收前提交总数：28
- Git tree：`3dbe13b1f6f9f35e79372d41f17ed82a20283c7e`
- 源实现tracked files：468

## 4. 既有冻结基线

M0标签`m0-engineering-foundation`是annotated tag：对象`a017a9167aefe09b6ee4026a20dac4cc4ce33780`，目标`a9a3a6ff361a610aac6ef66a98deed60efccd715`。M1标签`m1-project-foundation`是annotated tag：对象`e7a21496565d57f59e34242770c9cc29131157da`，目标`15bc7c559cd7021ab409e21bde93a7bf9853e7ce`，消息`M1 project foundation accepted`。六份M0/M1冻结文件相对各自标签均无差异。

## 5. M2范围

M2覆盖Story Bible不可变领域模型、Project单向归属、三表事务持久化、应用命令与查询、四条当前资源HTTP操作、React纯文本创建与完整修订，以及两条只读Revision历史GET和历史页面。真实性ID为继承的PRJ-001至PRJ-007与新增的STB-001至STB-003，没有STB-004。

## 6. M2明确不做

M2不包含Character及关系、World、Location、Organization、Power System、Ability、Item、结构化Story Bible区块、Markdown或富文本、Revision Diff/回滚/恢复/采用/编辑/删除、Story Bible删除/归档/恢复、自动保存、本地草稿持久化、AI设定生成、Outline、Volume、Chapter、章节正文、Review、Canon、Style、Analytics、Workflow、三区、分支、审批、Codex、Agent、Skill、Prompt管理、安装器、CI/CD、云同步或多用户账号。

## 7. 领域模型验收

`StoryBibleId`、`StoryBibleRevisionId`、`StoryBibleTitle`、`StoryBibleContent`、Stable Object、Revision、Head与Aggregate不变量全部通过。初始RevisionNumber和ConcurrencyVersion均为1；追加严格递增并采用完整替换；旧Aggregate和旧Revision保持不可变；stale检查先于Clock和Revision ID Factory，时钟回退被拒绝。

## 8. Project归属边界

Story Bible只保存到Project的单向规范标识引用，不导入Project服务或Repository，不修改Project正文或版本。不存在Project时创建失败；存在Project但尚无Story Bible与Project不存在保持不同错误语义。

## 9. 数据库Schema

Alembic head精确为`0003_create_story_bible_foundation`。正式Metadata精确为`projects`、`project_revisions`、`project_heads`、`story_bibles`、`story_bible_revisions`、`story_bible_heads`六表，无0004。SQLite启用WAL与foreign keys。

## 10. 一Project一Story Bible

Story Bible对Project的外键、Project唯一约束和Head复合所有权外键均通过迁移、ORM、Repository与真实SQLite测试；一个Project至多拥有一个Story Bible，跨属Head被数据库约束拒绝。

## 11. Revision不可变性

`trg_project_revisions_no_update`、`trg_project_revisions_no_delete`、`trg_story_bible_revisions_no_update`和`trg_story_bible_revisions_no_delete`四个触发器均存在并有效，Revision UPDATE与DELETE均被拒绝。

## 12. Migration循环

独立临时SQLite数据库从空库执行0001、0002、0003，再downgrade到0002并re-upgrade到0003。0003阶段六表与四触发器精确；downgrade只移除Story Bible三表与两个Story Bible触发器，保留Project三表和两个Project触发器；re-upgrade完整恢复且无示例数据。专项测试2项全部通过。

## 13. Repository事务

原子create/get/get_for_project/append、独立Session生命周期、Project不存在与重复归属、Revision或Head晚期失败完整回滚、损坏检测和安全错误均通过。所有Session关闭，正文、SQL和路径不进入错误。

## 14. 双CAS

修订同时执行Stable Object CAS与Head CAS；任一CAS失败都不产生残留Revision或部分Head变化，Repository以事务返回的Aggregate作为最终权威。

## 15. 并发冲突

两个独立Repository/Session以相同expected version并发时，恰好一个成功、一个抛出保留expected/actual的`ConcurrencyConflict`；无SQLite lock错误、无自动重试、失败正文和Revision ID不落库。

## 16. 应用层

不可变Create/Revise命令、Get/GetForProject查询、只含原语的`StoryBibleSnapshot`、显式Aggregate映射、Command Service和Query Service全部通过。应用层只依赖领域公开类型和Repository契约，导入无数据库、迁移、路由、Clock或ID副作用。

## 17. 创建副作用顺序

顺序固定为命令精确类型、ProjectId、Title、Content、Clock一次、Story Bible ID Factory一次、Revision ID Factory一次、纯领域创建、Repository.create一次、映射Repository返回Aggregate。任何前置失败阻止后续副作用，创建前不预查询。

## 18. 修订副作用顺序

顺序固定为命令精确类型、StoryBibleId、ConcurrencyVersion、Title、Content、Repository.append_revision一次、显式映射。服务不预查询、不自行调用Clock或Revision Factory，而是把注入对象交给Repository以保留事务内stale优先级。

## 19. 当前HTTP接口

Story Bible四条当前资源操作全部通过：按Project创建与读取、按Story Bible ID读取与完整替换修订。创建返回201、相对Location和强ETag；读取与修订返回当前权威Snapshot。production API总数精确为15。

## 20. ETag与If-Match

创建与当前读取返回强ETag；PUT必须使用规范`If-Match: "N"`。缺失前置条件返回428、非法格式返回400、stale返回412且expected/actual准确，不进行预读、自动重放、重试或合并。

## 21. HTTP安全边界

写请求要求本地Security Session、CSRF和可信Origin；所有只读GET无需CSRF。服务只绑定`127.0.0.1`，Host校验启用，CORS无通配符且credentials关闭，production docs/OpenAPI关闭；未迁移数据库安全返回503且不自动迁移。

## 22. 前端创建

Project详情提供真实入口；尚无Story Bible时展示创建状态，一次POST成功后直接采用返回资源和ETag，不额外GET。409与写结果未知均保留用户输入并提供明确核实动作。

## 23. 前端修订

编辑基线、dirty判定和一次PUT使用同一内存ETag；保存前不GET。成功更新版本；写结果未知保留草稿；没有自动保存、自动重试或自动合并。

## 24. 412冲突

412保留草稿与旧baseline，不自动GET或PUT。用户必须显式读取服务器最新版，并选择采用服务器版本或保留草稿重建baseline，再手动保存。

## 25. Revision历史后端

历史Reader与写Repository分离。135项Story Bible历史专项全部通过，专项采集的10个生产模块statements和branches均为100%。列表不读取content，不使用COUNT或OFFSET；单Revision正文按需读取。

## 26. Revision历史前端

历史页先按Project读取Story Bible，再取第一页；列表严格降序，当前Revision标记准确，加载更多保留已有项并用同一cursor重试，正文仅在选择后读取。24项专项全部通过，statements 96.03%、branches 91.30%、functions 100%、lines 96.03%。

## 27. cursor与Keyset分页

cursor严格、规范并绑定Story Bible；`limit`默认20、最大100，以`limit + 1`确定`has_more`，条件严格小于cursor位置。21+ Revision分页无重复遗漏；cursor不是跨请求快照，新Revision不会破坏旧cursor的确定性边界。

## 28. Head权威

当前Revision只由`story_bible_heads`指针确定，不以最大RevisionNumber替代。历史列表和单Revision读取先验证Stable Object，再以Head标记当前项；数据损坏使整次读取失败。

## 29. 浏览器存储与日志隐私

正文、草稿、ETag、cursor与选择项只保存在当前JavaScript/React内存，不写localStorage、sessionStorage、IndexedDB或URL。日志不记录Session、CSRF、If-Match、ETag、cursor、正文或草稿；生产代码不使用`dangerouslySetInnerHTML`。

## 30. 架构边界

领域、Repository契约、应用、持久化、Web和前端依赖方向均由AST与受控非法样例门禁验证。SQLAlchemy隔离在持久化适配器，FastAPI/Pydantic隔离在Web，组合根显式装配；UI不直接访问SQLite，其他模块不写Story Bible三表。

## 31. 依赖安全

Python依赖完整性检查通过；npm生产依赖审计为0漏洞。React Router保持8.3.0，没有新增Python或npm依赖，也没有修改锁文件。

## 32. 后端完整测试与覆盖率

三次完整门禁中的最终结果为1655项后端测试全部通过。覆盖率为statements 95.99%、branches 90.66%（6263 statements、251 missed；1434 branches、120 partial）。Ruff、mypy、格式、仓库卫生、安全与架构检查均通过。

## 33. 前端完整测试与覆盖率

36个前端测试文件、354项测试全部通过。最终依赖审计加E2E门禁记录为statements 96.26%、branches 91.85%、functions 99.45%、lines 96.28%；格式、ESLint、TypeScript、构建、架构与安全检查均通过。

## 34. E2E

17个Playwright场景全部通过，包含`E2E-INT-013`对21项Story Bible历史、20+1分页、按需正文、无历史Security Session、无浏览器持久化及真实Head/Revision状态的验证。开发与集成模式的自有服务、端口和数据根均完成清理。

## 35. 三种完整质量门

- `.\scripts\quality_gate.ps1`：通过。
- `.\scripts\quality_gate.ps1 -IncludeE2E`：通过，17/17 E2E。
- `.\scripts\quality_gate.ps1 -IncludeDependencyAudit -IncludeE2E`：通过，npm生产依赖0漏洞且17/17 E2E。

## 36. 警告与临时资源

后端完整测试有4条非阻断弃用警告：1条Starlette `httpx/TestClient`弃用警告，3条Python 3.12 SQLite默认datetime adapter弃用警告（2条Project损坏测试、1条Story Bible Head非最大Revision测试）。未发现功能失败；任务专属临时根、SQLite及sidecar、Playwright产物、服务与端口在验收结束后精确清理。

## 37. 已知非阻断风险

上述4条上游/测试夹具弃用警告需要在未来独立维护任务中处理；本次禁止顺手修改。历史cursor是定位边界而非数据库快照；M2纯文本模型没有结构化语义、Diff、恢复或本地草稿持久化。

## 38. 后续M3边界与冻结政策

`m2-story-bible-foundation`是不可移动、不可覆盖、不可重建的历史冻结标签；本报告、Manifest和清单未来不得改写。后续可用新任务和新提交扩展Story Bible，缺陷也必须通过新任务修复，不得amend或重写M2事实。M0、M1标签继续永久保留；M2冻结不表示仓库停止开发。

## 39. 正式验收声明

M2 Story Bible基础能力正式验收通过。
该结论代表Story Bible从不可变领域模型、事务持久化、应用用例、HTTP API、React创建与修订流程到只读Revision历史形成真实可验证闭环，不代表Character、世界观结构化模型、规划、章节写作、审校、Canon、Codex、Agent或完整AI网文产品已经完成。
