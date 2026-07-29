# Character持久化基础

本文档记录DEV-3.2建立的内部持久化边界。它把DEV-3.1的不可变Character聚合保存到SQLite，但不提供应用服务、DTO、HTTP API、前端页面、角色列表或用户可见能力。

## 所有权与基数

Character是独立业务模块，Project只通过稳定`ProjectId`成为其所有者。关系为：

```text
Project 1 → 0..n Character
Character 1 → 1..n CharacterRevision
Character 1 → 1 CharacterHead
```

同一Project可以拥有任意多个Character，也允许同名Character；身份唯一性只由`CharacterId`决定。Repository创建时只读Project是否存在，绝不修改Project三表。删除拥有Character的Project受外键`RESTRICT`保护。

## 三表结构

`characters`保存`id`、`project_id`、`concurrency_version`、`created_at`和`updated_at`。`project_id`只有非唯一索引`ix_characters_project_id`，不存在一Project一Character约束。

`character_revisions`保存`id`、`character_id`、`revision_number`、`name`、`role`、`profile`和`created_at`。每一行都是完整角色卡，不是Patch。`(character_id, revision_number)`和`(character_id, id)`分别唯一；名称、角色、正文长度及正RevisionNumber由数据库约束提供纵深保护。

`character_heads`保存`character_id`、`revision_id`和`updated_at`。复合外键`(character_id, revision_id)`保证Head只能指向同一Character拥有的Revision。当前Revision只由Head决定，不能以最大RevisionNumber推断。

## 不可变Revision

迁移创建两个稳定触发器：

```text
trg_character_revisions_no_update
trg_character_revisions_no_delete
```

直接SQL和ORM发出的UPDATE或DELETE都会以固定安全消息`Character revisions are immutable`失败。它们与Project、Story Bible的四个既有触发器共同构成六个Revision不可变触发器。降级0004只删除Character拥有的对象，不改变既有触发器。

## ORM与显式Mapper

`CharacterRecord`、`CharacterRevisionRecord`和`CharacterHeadRecord`没有ORM relationship、业务方法、自动默认值或用户数据repr。Mapper逐字段转换领域对象与Record，不使用反射或序列化捷径。数据库行恢复时会重新执行ID、值对象、UTC时间和Aggregate全部不变量；不能形成一致聚合时统一抛出安全的`CharacterDataCorruption`。

Record只在Session内使用，Repository返回的是脱离Session的不可变`CharacterAggregate`。关闭Session后仍可安全读取返回对象。

## Repository契约

纯Python `CharacterRepository` Protocol只定义：

```text
create
get
append_revision
```

当前没有按Project查询、角色列表、历史列表、分页、删除、归档或恢复。契约不导入SQLAlchemy、Session、迁移或具体实现。

`SqlAlchemyCharacterRepository`是模块内部适配器。每次调用都从注入的Session factory创建独立Session；Repository不共享Session、不缓存Aggregate、不使用全局锁、不读取环境变量，也不执行迁移。

## 创建事务

`create()`先在进入数据库前验证初始Aggregate必须为version 1/revision 1，然后以固定顺序执行：

```text
BEGIN IMMEDIATE
→ 检查Project存在
→ 检查Character ID未占用
→ INSERT characters
→ INSERT character_revisions
→ INSERT character_heads
→ COMMIT
```

Project不存在抛出`CharacterProjectNotFound`，Character ID重复抛出`CharacterAlreadyExists`。Revision ID冲突、数据库约束或任何晚期失败都会rollback，三表不会留下部分数据。角色卡正文不会进入错误消息。

## 当前读取

`get()`只接受精确`CharacterId`，用一条外连接SELECT同时读取稳定对象、Project存在性、Head和Head指向的Revision。不存在的Character返回`None`；存在稳定行但Project、Head或Revision缺失、所有权不一致、值或时间非法时抛出`CharacterDataCorruption`。数据库失败抛出安全的`CharacterRepositoryError`，不得伪装成不存在。

读取不加载历史、不执行COUNT、不写表。显式Head即使不是最大RevisionNumber，也仍是当前权威。

## 追加事务与副作用顺序

`append_revision()`要求完整的新`name`、`role`和`profile`，并以固定顺序执行：

```text
验证所有输入
→ BEGIN IMMEDIATE
→ 读取当前Aggregate
→ 检查expected version
→ 调用Clock一次
→ 调用Revision ID Factory一次
→ 运行纯领域追加
→ INSERT新Revision
→ Stable Object版本CAS
→ Head指针CAS
→ COMMIT
```

不存在时抛出`CharacterNotFound`。stale检查先于Clock和Factory，因此stale请求不生成ID、不读取时间、不写Revision，也不自动重试、合并或补齐旧值。成功时Clock和Factory各调用一次。

Stable Object与Head都使用compare-and-swap。任一CAS失败都会回滚新Revision和全部指针变化；Stable CAS miss重新读取实际版本并抛出保留expected/actual的`ConcurrencyConflict`，Head CAS miss视为数据损坏。并发由SQLite事务与双CAS保证，不使用sleep或全局Python锁。

Repository返回的成功Aggregate来自本次事务的完整领域转换，旧Revision永不修改。空role和空profile代表明确的完整替换。

## 错误与隐私

持久化边界使用以下安全错误：

- `CharacterAlreadyExists`
- `CharacterProjectNotFound`
- `CharacterNotFound`
- `CharacterDataCorruption`
- `CharacterRepositoryError`
- 共享`ConcurrencyConflict`

错误不包含name、role、profile、SQL、数据库路径、底层异常文本、对象repr、HTTP状态或API错误码。已知领域错误保持类型；基础设施异常使用异常链保留内部诊断，但公开消息固定。

## 迁移与Metadata

迁移链固定为：

```text
0001_initial_baseline
→ 0002_create_project_foundation
→ 0003_create_story_bible_foundation
→ 0004_create_character_foundation
```

正式Metadata精确包含九张业务表：

```text
character_heads
character_revisions
characters
project_heads
project_revisions
projects
story_bible_heads
story_bible_revisions
story_bibles
```

应用启动和导入Character领域都不会自动迁移、建表、连接数据库或注册Character路由。迁移必须由操作者对明确数据库显式执行。

## 架构边界

Character领域仍只依赖标准库、共享`domain`、自身领域和`ProjectId`。Repository契约也保持纯Python。只有`character.persistence`可以依赖SQLAlchemy、通用`db`适配层、自身领域/契约，以及为了外键存在性读取而使用的Project Record。专用`character.persistence.list_reader`可以向内实现纯应用层`CharacterListReader`端口并返回脱离Session的列表模型；其他持久化代码不得反向依赖应用层。持久化层不得导入Project Repository、Web层或Story Bible。

`db.model_registry`确定性注册Project、Story Bible和Character的九张表，但不连接数据库。Project、Story Bible、通用`domain`和Character领域均不得反向依赖Character持久化。

## 测试和当前限制

专项测试覆盖迁移循环、三表/索引/约束、显式Mapper、创建与读取、完整替换追加、失败回滚、损坏矩阵、Revision不可变触发器和两个独立Repository的确定性并发。测试只使用迁移到0004的独立临时SQLite数据库，结束后清理数据库及sidecar。

DEV-3.3已在写Repository之外新增独立只读列表适配器。它使用普通独立Session、先验证Project存在性、再从Stable Object连接Head所指向的当前Revision，每页最多两个业务SELECT；固定按`created_at DESC, character_id DESC`执行复合Keyset分页，并且不读取profile、不使用COUNT或OFFSET。Head而不是最大RevisionNumber是当前列表的唯一权威。

当前明确没有：

- Character DTO、HTTP API、Router或组合根接线；
- Character前端入口、Revision历史或关系图；
- 头像、附件、结构化年龄/性别/能力/关系；
- World、PowerSystem、规划、章节、三区、审批、Codex、Agent或AI生成。

应用层和列表边界见[Character应用用例](CHARACTER_APPLICATION.md)。现有内部能力不构成用户功能；DEV-3.4仍需独立编号任务授权。
