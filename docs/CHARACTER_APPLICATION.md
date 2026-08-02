# Character应用用例

## 职责与边界

`aiwebnovel.character.application`在纯Character领域与事务`CharacterRepository`之上提供内部应用用例。它只定义传输原语命令、类型化查询、脱离持久化的不可变读取模型、显式Mapper和无状态服务，不依赖SQLAlchemy、FastAPI、Pydantic、数据库Session或具体适配器。

DEV-3.4已在本层之外增加独立`character.web`适配器和组合根接线；DEV-3.5通过该HTTP边界建立Character当前前端；DEV-3.6在应用层新增独立只读历史端口与服务。应用层自身仍不依赖FastAPI、Pydantic或前端。当前没有历史写入、关系、World、PowerSystem、规划、章节、Codex、Agent或AI生成。

## Commands与当前读取

`CreateCharacterCommand`精确包含：

```text
project_id: str
name: str
role: str
profile: str
```

`ReviseCharacterCommand`精确包含：

```text
character_id: str
expected_version: int
name: str
role: str
profile: str
```

命令不可变，只保存外部传输原语，不生成ID、不访问数据库，也不携带Clock、Factory、Repository或Session。修订表示完整替换；空role和空profile是明确的新值，不表示保留旧值。

`GetCharacterQuery`只包含外部`character_id`字符串，用于读取一个Character的当前完整快照。`ListCharactersForProjectQuery`包含外部`project_id`、1至100的真整数`limit`和可选的类型化`CharacterListPosition`；默认limit为20，不接受bool、浮点、OFFSET、页码、搜索、过滤或排序选项。

## 不可变读取模型

`CharacterSnapshot`完整包含：

```text
character_id
project_id
current_revision_id
revision_number
concurrency_version
name
role
profile
created_at
updated_at
revision_created_at
head_updated_at
```

所有ID在Snapshot中是规范字符串，版本是真正的正整数且相等，四个时间是aware UTC，并满足Stable、Revision与Head的时间一致性。Snapshot不暴露领域值对象、Aggregate、ORM、Session、ETag或历史。

`character_snapshot_from_aggregate()`精确验证`CharacterAggregate`类型并逐字段显式映射，不使用反射、`asdict()`、数据库、Clock或ID生成。Repository返回的Aggregate是创建和修订结果的最终权威，应用服务不会从写入前的Aggregate伪造成功Snapshot。

## 列表摘要、页面与位置

`CharacterListItem`精确包含：

```text
character_id
current_revision_id
revision_number
concurrency_version
name
role
created_at
updated_at
```

列表故意不包含profile，避免批量读取角色卡正文；也不包含Project ID副本、关系、能力、历史Revision或AI元数据。

`CharacterListPage`包含规范`project_id`、不可变Item tuple、可选`next_position`和`has_more`，不包含total或cursor字符串。页面验证ID唯一、严格降序、继续页位置等于本页最后一项、终页无位置且空页必须为`items=(), has_more=False, next_position=None`。

`CharacterListPosition`由精确`ProjectId`、aware UTC `created_at`和精确`CharacterId`组成，固定绑定一个Project。排序固定为：

```text
created_at DESC
character_id DESC
```

下一页使用严格复合Keyset：

```text
created_at < after.created_at
OR (
  created_at == after.created_at
  AND character_id < after.character_id
)
```

同一创建时间由规范Character ID文本稳定打破平局。位置不能跨Project复用；当前没有HTTP cursor编码。

## CharacterListReader端口

纯应用端口`CharacterListReader`只公开`list_for_project()`。它与写`CharacterRepository`分离，不提供写入、按ID读取、COUNT、OFFSET、搜索、过滤、profile或Revision历史。

`SqlAlchemyCharacterListReader`是持久化层中的独立只读适配器。每次调用创建并关闭独立Session，使用普通只读事务，不执行`BEGIN IMMEDIATE`、写入、自动迁移或重试。正常路径最多执行两个业务SELECT：

1. 验证Project存在；
2. 从Character Stable Object连接Head指向的当前Revision，按固定Keyset读取`limit + 1`。

第二个SELECT不选择profile，不执行COUNT或OFFSET。多取的一项只用于判断`has_more`，位置来自实际返回的最后一项。Project不存在抛出`CharacterProjectNotFound`；Project存在但无Character返回规范空页。同一Project允许多个Character和多个同名Character。

Head是当前Revision的唯一权威；Reader不以最大RevisionNumber推断当前值。缺少Head、Head指向错误、版本或时间不一致、非法字段等任一损坏都会使整页以`CharacterDataCorruption`失败，不会静默跳过损坏项或泄漏name、role、profile。

## Command Service

`CharacterCommandService`显式注入：

```text
CharacterRepository
Clock
Character ID Factory
Character Revision ID Factory
```

创建固定顺序为：

```text
精确验证command
→ 解析ProjectId
→ 构造CharacterName
→ 构造CharacterRole
→ 构造CharacterProfile
→ 调用Clock一次
→ 调用Character ID Factory一次
→ 调用Revision ID Factory一次
→ 纯领域初始创建
→ Repository.create一次
→ 显式映射Repository返回Aggregate
```

输入或早期依赖失败会阻止后续副作用；创建前不执行同名查询、列表查询或任何预读，不自动重试重复ID。两个Factory返回值必须是精确领域ID类型，错误不会调用 hostile对象的repr。

修订固定顺序为：

```text
精确验证command
→ 解析CharacterId
→ 构造ConcurrencyVersion
→ 构造CharacterName
→ 构造CharacterRole
→ 构造CharacterProfile
→ Repository.append_revision一次
→ 显式映射Repository返回Aggregate
```

修订前不调用`get()`或列表Reader，不预检查版本、不合并、不重试。应用服务把同一Clock与Revision ID Factory传入Repository，但不自行调用；Repository在事务内继续保证stale优先级。`ConcurrencyConflict`保留expected/actual并原样传播。

## Query Service与错误隐私

`CharacterQueryService`显式依赖`CharacterRepository`契约和`CharacterListReader`端口。按ID查询只解析ID并调用`Repository.get()`一次，`None`转为`CharacterNotFound`；列表查询只解析Project和边界并调用Reader一次。两个查询不互相调用，不写入、不生成ID、不调用Clock、不缓存或重试。

领域、并发、缺失、损坏和持久化错误保持稳定类型与安全消息。应用层不拼接底层异常文本，不输出SQL、路径、对象repr或角色卡正文。

## 当前限制与下一步

DEV-3.4只在应用层外增加四条Character HTTP操作、严格DTO/游标/错误映射和组合根，不修改0004、九表Metadata、应用命令与Repository事务语义或前端路由。完整传输契约见[Character HTTP API](CHARACTER_HTTP_API.md)。

DEV-3.5已建立Character当前页面。DEV-3.6另增`CharacterRevisionHistoryReader`端口、不可变历史位置/摘要/页/详情模型、两个只读Query及`CharacterRevisionHistoryQueryService`；列表和详情各只调用Reader一次，列表不含profile，详情按RevisionNumber读取完整profile，Head决定current。完整契约见[Character不可变Revision历史](CHARACTER_REVISION_HISTORY.md)。当前仍不存在历史恢复、回滚、Diff、编辑或删除，以及关系、归档、结构化年龄/性别/能力、World、PowerSystem、规划或AI生成。
