# Character纯领域模型

本文档记录DEV-3.1建立的`aiwebnovel.character`内部领域契约。它只证明Character的身份、不可变Revision和乐观并发规则已经形成；当前没有Character数据库表、Repository、应用服务、HTTP API、前端入口或用户可见能力。

## 模块职责与归属

Character是独立业务模块，不是Story Bible内部嵌套值对象。它拥有自己的稳定身份、完整角色卡Revision、当前Revision指针和一致Aggregate；即使未来从Story Bible页面进入，数据权威仍属于Character。

依赖方向固定为：

```text
Character Domain → ProjectId
```

`ProjectId`只表达稳定归属。Character不读取Project状态、不验证Project存在、不修改Project，也不复制`prj`解析规则。Project、Story Bible和通用`domain`不得反向依赖Character。Character不依赖Story Bible ID、实体、应用、持久化或Web层。

## 标识符

| 类型 | 前缀 | 语义 |
| --- | --- | --- |
| `CharacterId` | `chr` | Character稳定身份 |
| `CharacterRevisionId` | `crv` | 单个不可变Revision身份 |

两种ID复用共享Prefixed ULID，实现严格前缀、大小写、长度和规范文本解析。`new()`生成规范ID，`parse()`拒绝非规范文本、其他模块ID、裸ULID、空白、控制字符、非字符串和bool。错误固定且不回显输入。

## 角色卡值

`CharacterName`要求精确字符串，移除Unicode首尾空白，规范结果为1至120个Unicode代码点；内部普通空格、大小写和emoji保持原样，控制字符及Unicode行/段落分隔符被拒绝。同一Project内同名Character合法，身份只由`CharacterId`决定。

`CharacterRole`是用户自由填写的叙事角色，不是“主角/配角/反派”枚举。它要求精确字符串，移除Unicode首尾空白，最多120个代码点；空字符串合法，内部空格和大小写保持原样。

`CharacterProfile`是最多50000个Unicode代码点的纯文本正文。空字符串合法；CRLF和单独CR规范化为LF；普通空格、首尾空格、Tab、LF和空行保持原样。除Tab和LF外的C0控制字符、C1控制字符及Unicode行/段落分隔符被拒绝。它不执行trim、截断、Markdown解析、HTML处理、AI抽取或结构化字段解析。

当前角色卡快照只有：

```text
name
role
profile
```

当前不建立结构化年龄、性别、外貌、能力、阵营、位置、物品或关系字段，也不使用无边界JSON容器。用户可以在纯文本profile中自行描述这些内容，但系统不解释其结构。任何新增结构化属性都必须由后续编号任务和新Revision契约明确授权。

## Stable Object、Revision与Head

`Character`是稳定对象，只保存`id`、`project_id`、`concurrency_version`、`created_at`和`updated_at`。身份与Project归属创建后不可改变；名称、角色和正文不存放在稳定对象中。

`CharacterRevision`保存`id`、`character_id`、`revision_number`、`name`、`role`、`profile`和`created_at`。每个Revision都是完整、不可变角色卡快照，不是Patch，不包含Project ID副本、父Revision、Diff、作者、审批、AI元数据、关系、ORM或Session。

`CharacterHead`只保存`character_id`、当前`revision_id`和`updated_at`，是当前Revision的显式权威指针。不能以最大RevisionNumber推断Head。

## Aggregate不变量

`CharacterAggregate`只组合当前`Character`、`CharacterHead`和`CharacterRevision`，不嵌入历史。它验证：

1. Head和Revision都属于同一Character；
2. Head指向当前Revision；
3. `ConcurrencyVersion == RevisionNumber`；
4. Character、Head与当前Revision更新时间相同；
5. Character创建时间不晚于更新时间；
6. 当前Revision不早于Character创建时间；
7. 所有时间均为aware UTC，其他aware时区规范化为UTC。

损坏状态只抛出稳定的`InvalidCharacterState`，不披露name、role或profile。

## 纯转换与并发

`create_initial_character()`完全使用调用方提供的ID、值对象和时间，创建Revision 1与ConcurrencyVersion 1；Character创建/更新时间、Revision创建时间和Head更新时间为同一时刻。函数不调用Clock、不生成ID、不访问Project、Story Bible、数据库或文件系统。

`append_character_revision()`先精确验证Aggregate与expected version，再比较expected和actual。stale时复用`ConcurrencyConflict`并保留安全的expected/actual整数；该检查优先于clock rollback、重复Revision ID和后续状态构造。成功时RevisionNumber和ConcurrencyVersion各递增1，Head指向新Revision，Character身份、Project归属和创建时间保持不变。

`now < updated_at`视为clock rollback并拒绝；相等时间合法。追加不会自动重试、合并或补齐旧值。

每次追加固定使用：

```text
新name + 新role + 新profile = 新Revision完整角色卡
```

`None`、缺字段、Patch、JSON Patch、字段级merge和旧值补齐均不属于领域契约。空role和空profile是明确的完整替换值，name仍不得为空。旧Aggregate、旧Character、旧Head和旧Revision全部保持不可变。

## 错误隐私与架构边界

值错误分别为`InvalidCharacterName`、`InvalidCharacterRole`和`InvalidCharacterProfile`；损坏状态为`InvalidCharacterState`；标识符复用`InvalidDomainIdentifier`；并发复用`ConcurrencyConflict`；时间遵循共享UTC政策。错误不包含HTTP状态、API错误码、数据库、SQL、路径、对象repr或角色卡正文。

Character生产代码只允许导入标准库、`aiwebnovel.domain`、自身模块和`aiwebnovel.project.identifiers.ProjectId`。AST门禁拒绝SQLAlchemy、Alembic、FastAPI、Pydantic、通用基础设施、Project实体/Repository/Application/Persistence/Web、Story Bible及反向依赖，并阻止`characters`、`character_card`、`character_cards`、`person`、`persona`和`cast`等并存生产包。

导入`aiwebnovel.character`不会连接或创建数据库、读取数据根、创建目录、注册路由、调用Clock、生成ID、修改Project/Story Bible状态或改变正式Metadata。

## 当前限制与下一步

当前明确没有：

- Character数据库表、索引、触发器或迁移；
- Character Repository、应用服务、DTO、API或前端；
- 角色列表、关系、关系图、头像、附件或结构化属性；
- World、PowerSystem、规划、章节、三区、审批、Codex、Agent或AI生成。

DEV-3.2预期只在新的明确任务授权下建立Character持久化基础；它不得通过本领域文档被视为已授权，也不得改写本任务的不可变Revision和模块依赖契约。
