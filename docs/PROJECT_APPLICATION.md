# Project应用用例

DEV-1.4在Project领域模型与事务Repository之上建立纯Python应用层。DEV-1.5保持该层不含HTTP、Pydantic或SQLAlchemy，并由独立`project.web`适配器与`main`组合根调用。DEV-1.6在同一纯Python边界增加列表读取模型、专用Reader端口和查询服务，不把列表塞入聚合写Repository。

## 命令、查询与读取模型

命令表示写入意图，查询表示只读意图，二者都只是不可变的原始输入，不在构造时读取时钟、生成ID、访问数据库或创建领域值对象。`ProjectSnapshot`是成功用例的不可变读取结果，不是命令、领域Aggregate、ORM Record或JSON字符串。

`CreateProjectCommand`只有：

- `title: str`；
- `description: str = ""`。

调用者不能提供Project ID、Revision ID、并发版本或时间；应用用例负责生成这些值。

`ReviseProjectCommand`只有：

- `project_id: str`；
- `expected_version: int`；
- `title: str`；
- `description: str = ""`。

修订采用完整替换语义：每次必须同时提交完整标题和完整简介，`None`不表示保留旧值，也没有JSON Patch、字段合并、自动重试或自动合并。Revision ID、下一修订号、下一并发版本和更新时间不能由调用者指定。

`GetProjectQuery`只有`project_id: str`，不包含Session、分页、历史或删除状态选项。

## ProjectSnapshot

读取模型精确包含：

- `project_id: str`；
- `current_revision_id: str`；
- `revision_number: int`；
- `concurrency_version: int`；
- `title: str`；
- `description: str`；
- `created_at: datetime`；
- `updated_at: datetime`；
- `revision_created_at: datetime`；
- `head_updated_at: datetime`。

唯一显式映射`project_snapshot_from_aggregate()`逐字段把ID转为规范文本，把修订号和并发版本转为真正的整数，把文本值转为字符串，并保留aware UTC时间。映射不使用`asdict()`、反射、Repository或数据库，不复制历史列表，也不尝试修复无效Aggregate。

Snapshot不暴露领域对象或ORM，是为了避免把内部不变量、Session生命周期、惰性加载状态和持久化实现泄漏到未来边界。成功返回后即使Repository的Session已经关闭，Snapshot仍可独立使用；当前不建立全局JSON编码器。

## 创建用例与副作用顺序

`ProjectCommandService.create_project()`固定按以下顺序执行：

```text
验证命令精确类型
→ 构造ProjectTitle
→ 构造ProjectDescription
→ 读取Clock一次
→ 生成ProjectId一次
→ 生成ProjectRevisionId一次
→ 创建初始ProjectAggregate
→ repository.create()一次
→ 显式映射ProjectSnapshot
```

标题或简介无效时不会调用时钟、ID工厂或Repository；时钟失败时不会生成ID；Project ID生成失败时不会生成Revision ID；Revision ID生成失败时不会调用Repository。Repository返回的安全领域或持久化错误原样传播，不会伪装为成功。

## 修订用例与并发

`ProjectCommandService.revise_project()`固定按以下顺序执行：

```text
验证命令精确类型
→ 解析ProjectId
→ 构造ConcurrencyVersion
→ 构造ProjectTitle
→ 构造ProjectDescription
→ repository.append_revision()一次
→ 显式映射ProjectSnapshot
```

应用层把Clock和Revision ID工厂传给Repository，但不预先调用它们。应用层也不会先执行`get()`再执行`append_revision()`：Repository必须在同一个`BEGIN IMMEDIATE`事务中读取当前状态、拒绝stale版本并执行Project与Head双CAS，应用层预读会制造读后写竞态且无法替代事务内检查。

每个写命令只对应一个Repository写操作和一个原子事务。应用层不打开Session、不执行SQL、不提交或回滚、不跨Repository写入、不补偿、不重试，也不建立Saga或Unit of Work。

stale写入原样传播`ConcurrencyConflict`，保留`expected_version`与`actual_version`。缺失写入原样传播`ProjectNotFound`；损坏持久化状态原样传播`ProjectDataCorruption`；其他已经安全转换的`ProjectRepositoryError`同样原样传播。本层不增加HTTP状态码或API错误码。

## 查询用例

`ProjectQueryService.get_project()`先验证查询精确类型并解析`ProjectId`，然后只调用一次`repository.get()`。存在时显式映射当前Snapshot，不存在时返回`None`；它不创建Project、不写入、不调用时钟或ID工厂、不更新访问时间、不加载历史，也不缓存结果。

## 列表查询用例

`ProjectListPosition`只保存aware UTC `created_at`和规范Project ID文本。`ListProjectsQuery`只包含limit与可选after，默认20、最小1、最大100，并拒绝bool、浮点和其他隐式整数。`ProjectListItem`精确保存当前Revision摘要，不包含description、ORM、领域值或Session；`ProjectListPage`使用tuple items，只在确有下一页时保存最后一个实际item的位置。

专用`ProjectListReader`是应用端口，只提供`list_page(limit, after)`，不改变现有写Repository契约，也不提供total、任意排序或过滤。`ProjectListQueryService.list_projects()`验证查询精确类型与limit后只调用Reader一次；它不调用`ProjectRepository.get()`、不执行N次聚合读取、不预取、不缓存、不生成ID或时间，也不吞掉安全持久化与损坏错误。SQLAlchemy实现属于Project持久化层，HTTP cursor属于Web传输层。完整排序、Keyset与页间变化语义见[Project列表读取](PROJECT_LISTING.md)。

## 架构取舍与当前边界

当前命令与查询数量很少，直接服务契约更明确，因此不建立通用命令总线、查询总线、Mediator或通用CQRS框架。命令和查询职责分离不等于引入CQRS基础设施，也不改变Project对三张表的唯一所有权。

DEV-1.5已在应用层之外建立创建、详情和完整修订接口；DEV-1.6新增列表接口、严格cursor与独立列表Reader装配。应用层本身仍不知道HTTP状态、ETag、cursor文本、Pydantic、具体SQLAlchemy实现或app state。当前仍没有Project前端页面、历史、删除、归档、PATCH、搜索、筛选、表单或保存按钮；详细HTTP契约见[Project HTTP API](PROJECT_HTTP_API.md)。
