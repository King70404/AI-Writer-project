# Story Bible应用用例

DEV-2.3在纯领域模型与事务Repository之上建立`aiwebnovel.story_bible.application`。该包只表达内部应用命令、当前快照查询和事务级业务用例，不提供DTO、HTTP API、组合根接线、前端页面或用户可见功能。

## Commands与Queries边界

命令和查询都是`frozen=True, slots=True`的不可变dataclass，只保存传输边界原语。构造命令或查询不会解析领域值、读取数据库、调用时钟或生成ID。

- `CreateStoryBibleCommand(project_id, title, content)`表示为一个Project创建唯一Story Bible；
- `ReviseStoryBibleCommand(story_bible_id, expected_version, title, content)`表示完整替换当前标题和正文；
- `GetStoryBibleQuery(story_bible_id)`按Story Bible ID读取当前快照；
- `GetStoryBibleForProjectQuery(project_id)`按Project归属读取唯一当前快照。

使用字符串和整数等传输原语，是为了让应用边界不把领域对象、Repository、Session、Clock或Factory泄漏给未来传输层。所有外部值只在服务方法中按固定顺序转换，拒绝bool版本、隐式整数、非规范ID和非法文本，不执行`str()`、`int()`、trim正文、截断或自动修复。

## StoryBibleSnapshot

`StoryBibleSnapshot`精确包含：

```text
story_bible_id
project_id
current_revision_id
revision_number
concurrency_version
title
content
created_at
updated_at
revision_created_at
head_updated_at
```

三个ID是规范字符串，两个版本是真正正整数，标题和正文是普通字符串，四个时间保存为aware UTC。Snapshot重新验证ID、版本相等、标题与正文规则以及`created_at <= updated_at == revision_created_at == head_updated_at`，并使用不可变slots对象，不含Aggregate、领域值、ORM、Session、历史Revision、ETag或HTTP信息。

Snapshot不暴露领域或ORM对象，是为了固定应用读取契约，避免内部不变量、惰性加载、Session生命周期和持久化实现传播到未来边界。Repository关闭Session后，Snapshot仍可独立安全使用。

唯一映射函数`story_bible_snapshot_from_aggregate()`先要求精确`StoryBibleAggregate`，再逐字段显式转换。它不使用反射、`asdict()`或Pydantic，不访问数据库、时钟、Factory或Repository，也不修改Aggregate；Snapshot构造会再次执行自身不变量。

## Command Service

`StoryBibleCommandService`显式注入：

- `StoryBibleRepository`契约；
- `Clock`；
- `Callable[[], StoryBibleId]`；
- `Callable[[], StoryBibleRevisionId]`。

服务不创建Session、不commit或rollback、不执行迁移、不读取环境变量、不缓存、不记录正文、不自动重试，也不依赖SQLAlchemy具体Repository。不同服务实例可以绑定不同Repository、Clock与Factory。

创建副作用顺序固定为：

```text
验证命令精确类型
→ 解析ProjectId
→ 构造StoryBibleTitle
→ 构造StoryBibleContent
→ 调用Clock一次
→ 调用Story Bible ID Factory一次
→ 调用Revision ID Factory一次
→ 纯领域初始创建
→ Repository.create一次
→ 显式映射Snapshot
```

输入失败发生在全部外部副作用之前；Clock失败阻止两个Factory，Story Bible ID Factory失败阻止Revision Factory，Revision Factory或领域转换失败阻止Repository。Factory结果必须是精确ID类型，字符串、其他模块ID、`None`及伪装类型均以固定安全错误拒绝。创建前不调用`get()`或`get_for_project()`，也不重试重复ID。

修订副作用顺序固定为：

```text
验证命令精确类型
→ 解析StoryBibleId
→ 构造ConcurrencyVersion
→ 构造StoryBibleTitle
→ 构造StoryBibleContent
→ Repository.append_revision一次
→ 显式映射Snapshot
```

修订是完整替换，新title和新content共同形成完整Revision；空content是合法完整替换，不存在Patch、merge、旧值补齐或`None`保留。应用服务不在修订前GET，不自行调用Clock或Revision ID Factory，而是把构造时注入的同一对象传给Repository。这样，stale检查继续在Repository事务内优先于Clock、Factory和写入，避免读后写竞态并保持DEV-2.2的副作用顺序。

Repository返回的Aggregate是最终权威。创建和修订Snapshot都从Repository返回值映射，不能从写入前Aggregate直接构造，以免掩盖持久化层规范化、并发结果或损坏状态。

## Query Service

`StoryBibleQueryService`只注入`StoryBibleRepository`契约。它不创建Session、不调用Clock、不生成ID、不写入、不缓存或重试。

- 按ID读取：验证精确Query、解析StoryBibleId、调用`repository.get()`一次；`None`转换为`StoryBibleNotFound`；
- 按Project读取：验证精确Query、解析ProjectId、调用`repository.get_for_project()`一次；`None`转换为应用错误`StoryBibleForProjectNotFound`。

`StoryBibleProjectNotFound`表示Project本身不存在；`StoryBibleForProjectNotFound`只表示Project存在但尚无Story Bible。数据损坏和持久化失败不能伪装为不存在。

## 错误、并发与隐私

标识、标题、正文、状态、重复、归属、缺失、数据损坏、Repository失败和`ConcurrencyConflict`均保持原始安全类型。应用层不统一包装、不添加HTTP状态或API错误码、不拼接底层异常字符串、不泄漏SQL、路径、对象`repr`、标题或正文。stale冲突保留`expected_version`和`actual_version`，不自动重试、合并或覆盖。

自动测试使用`STORY_BIBLE_APPLICATION_SECRET_CANARY`验证命令、查询、Snapshot、Factory和Repository错误不会泄漏正文。成功Snapshot按职责包含正常用户标题与正文。

## 当前范围与DEV-2.4

当前没有Story Bible HTTP API、Pydantic DTO、Web错误映射、组合根装配、前端路由或页面，也没有历史列表、单Revision读取、删除、归档、恢复、Character、World、PowerSystem、Planning、三区、审批、Codex或Agent。内部应用用例不能登记为用户可见能力，`FEATURE_REALITY_MATRIX.md`保持不变。

DEV-2.4如被独立任务授权，预期只能在本应用契约之外定义明确的传输边界、错误映射和组合方式；其实际范围仍必须以对应任务包为准，DEV-2.3不预先创建DTO、API或前端。
