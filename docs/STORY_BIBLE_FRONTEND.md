# Story Bible 前端流程

DEV-2.5在不修改后端、Schema、迁移或Repository事务语义的前提下，为既有Story Bible HTTP API建立真实React用户流程。页面只管理一个Project唯一的纯文本Story Bible，不提供Revision历史、结构化设定或AI能力。

## 路由与入口

- 唯一路由是`/projects/:projectId/story-bible`，由Project详情页“查看 Story Bible”链接进入，并支持生产构建直接刷新。
- 路由参数必须是规范`prj_` ULID；非法值在任何网络请求前失败，既不自动修复也不回显原值。
- 前端总路由保持六条：`/`、`/projects`、Project详情、Project历史、Project Story Bible和通配404。没有独立Story Bible ID页、历史页、编辑子路由或设置页。

## 运行时契约与版本资源

Story Bible API客户端严格解析Snapshot的11个字段：三个规范ID、RevisionNumber、ConcurrencyVersion、title、content和四个aware UTC时间。对象不得有缺失或额外字段；两个版本必须是相等的正安全整数，所有ID、时间关系、title和content都重新验证。

`VersionedStoryBibleResource`把响应正文与同一响应的强ETag绑定。ETag只接受精确`"<positive-safe-integer>"`并必须等于正文`concurrency_version`；弱标签、列表、空白、零、前导零、小数、负数或溢出均不能进入页面状态。创建响应还必须是201且Location精确指向`/api/v1/story-bibles/{story_bible_id}`；GET和PUT分别要求200。

## 创建、读取与完整修订

首次进入只执行一次`GET /api/v1/projects/{project_id}/story-bible`。Project不存在与Project存在但尚无Story Bible分别显示；后者提供创建表单。创建正文只含完整`title`与`content`，一次POST成功后直接采用服务端返回的版本资源，不额外GET。

已有资源显示当前ID、RevisionNumber、ConcurrencyVersion及时间元数据，并用最后一次已确认资源作为内存编辑基线。保存一次PUT到稳定Story Bible ID，正文是完整标题和正文，`If-Match`只来自基线强ETag。PUT前不预读，不使用PATCH，不从旧正文补齐，不自动保存、重试、重放或合并。

## 输入与可访问状态

- title必须是字符串，trim后1至120个Unicode代码点；
- content必须是字符串，最多50000个代码点，CRLF/CR规范化为LF，空正文合法；
- 两个字段拒绝领域禁止的控制字符，不强转、截断或静默修复；
- 字段错误关联对应控件并聚焦首个无效输入；
- loading使用`role=status`，安全错误与冲突使用`role=alert`，提交中禁用相关控件；
- 创建、编辑、放弃、重载、采用服务器版本和保留草稿均使用真实语义控件，不创建空按钮或假状态。

## 写结果未知与412冲突

POST或PUT开始后的网络失败、abort、5xx或不可信成功响应可能意味着服务端已提交，因此统一进入结果未知状态。客户端保留提交草稿和旧基线，禁止自动再次写入。创建结果只能由用户显式重新读取Project的Story Bible核实。

合法412必须包含安全且一致的`expected_version`和`actual_version`。冲突时保留提交草稿与旧基线，不自动GET。用户点击“读取最新版本”后才按稳定Story Bible ID执行一次GET，并可选择：

1. 采用服务器版本：放弃草稿且不写入；
2. 保留草稿并以服务器版本建立基线：只更新基线，仍不写入；
3. 之后再次手动点击保存：使用最新ETag完整替换，形成新的Revision。

这不是自动合并；页面只并排展示服务器最新版本与本地草稿，选择权始终属于用户。

## 安全与架构边界

共享API层拥有唯一的规范ID、强ETag与进程内Security Session实现。Story Bible API层可依赖这些通用原语，但不得依赖React、Project功能、hooks、组件或页面；hook依赖API，组件依赖hook，页面负责组合。

GET不获取Security Session。POST/PUT先完成本地验证，再按需取得内存CSRF并仅发送一次。组件不得裸调用`fetch`或读取Cookie；CSRF、ETag、草稿、title和content不得写入`localStorage`、`sessionStorage`、IndexedDB、Cookie、URL、日志或诊断文件。错误只展示稳定安全文案和允许的request ID，不拼接服务端正文、异常字符串、SQL或路径。

## 验证与明确限制

Vitest专项覆盖严格契约、API协议、创建、编辑、冲突、路由和受控架构正负样例。`E2E-INT-012`使用真实production服务与迁移到0003的独立SQLite数据库，从UI创建Project和Story Bible v1，刷新、修订v2，经外部API形成v3，再由旧页面触发412、显式读取、保留草稿并手动保存v4；数据库验收确认一个Stable、四个不可变Revision、一个Head以及Project版本未变。

当前没有Story Bible Revision列表或单Revision读取、历史页面、Diff、回滚、恢复、删除、归档、Character、World、PowerSystem、规划、三区、审批、Codex、Agent、Skill、Prompt或AI生成。后续能力必须由独立编号任务授权。
