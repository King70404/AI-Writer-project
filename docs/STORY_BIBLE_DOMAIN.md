# Story Bible纯领域模型

DEV-2.1建立`aiwebnovel.story_bible`的纯领域契约。Story Bible是独立业务模块，负责一个Project内部故事设定文本的稳定身份、不可变修订和当前指针；Project只拥有Project自身数据，不拥有或修改Story Bible内容。

## 依赖方向与所有权

固定依赖方向是：

```text
StoryBible Domain → ProjectId
```

Story Bible只导入`aiwebnovel.project.identifiers.ProjectId`作为归属引用，不读取Project状态，不验证Project是否存在，也不调用Project Repository。Project和通用`domain`不得反向依赖Story Bible。跨模块存在性和持久化一致性留给后续应用与持久化边界处理。

Story Bible生产代码只可依赖Python标准库、`aiwebnovel.domain`、ProjectId和本模块内部文件；不得依赖SQLAlchemy、Alembic、FastAPI、Pydantic、数据库、Security、Storage、Project实体/Repository/Application/Persistence/Web或前端。

## 标识符

- `StoryBibleId`固定使用`sbl`前缀；
- `StoryBibleRevisionId`固定使用`sbr`前缀。

二者复用通用Prefixed ULID实现，不复制ULID、Crockford Base32或时间编码。`new()`生成规范文本，`parse()`只接受大小写、前缀、长度和字符均规范的完整文本；裸ULID、其他模块ID、小写ULID、空白、控制字符和非字符串都会以安全的`InvalidDomainIdentifier`拒绝。对象不可变，具有类型隔离的相等和哈希语义。

## 文本值

`StoryBibleTitle`是不可变标题值。它要求输入为字符串，先拒绝C0/C1控制字符及U+2028/U+2029，再移除Unicode首尾空白；结果必须包含1至120个Unicode代码点。内部普通空格和大小写保持不变，emoji按Python字符串中的Unicode代码点计数。它不生成默认标题，也不执行HTML、Markdown或内容过滤；失败抛出不回显输入的`InvalidStoryBibleTitle`。

`StoryBibleContent`是不可变纯文本快照。空字符串合法，最大长度为50000个Unicode代码点；CRLF和单独CR规范化为LF，普通空格、首尾空格、Tab、LF和大小写保持不变。除Tab和LF外的C0控制字符、全部C1控制字符及U+2028/U+2029均被拒绝。它不trim、不截断、不压缩空行，也不执行Markdown解析、HTML清理、敏感词过滤或AI抽取；失败抛出不回显正文的`InvalidStoryBibleContent`。

当前正文只是完整的纯文本设定快照，不是最终结构化世界观模型。DEV-2.1不提前创建Character、World、PowerSystem、Location、Organization、Ability、Item或其他结构，避免在相应业务规则尚未独立定义前形成错误所有权。

## 稳定对象、Revision与Head

`StoryBible`稳定对象只包含：

```text
id
project_id
concurrency_version
created_at
updated_at
```

它表达身份、Project归属和并发状态，不包含标题、正文、Revision列表、ORM、用户、权限、审批或Codex配置。标识和Project归属创建后不可改变；时间必须是aware datetime，非UTC时区会规范化为UTC，naive时间拒绝，且`created_at <= updated_at`。

`StoryBibleRevision`包含：

```text
id
story_bible_id
revision_number
title
content
created_at
```

每个Revision是创建后绝对不可变的完整标题和正文快照，没有`updated_at`、ConcurrencyVersion、ProjectId副本、父Revision、Diff、作者、审批或AI元数据。旧Revision永不被后续转换覆盖。

`StoryBibleHead`包含`story_bible_id`、`revision_id`和`updated_at`，是当前Revision的显式权威指针。当前Revision不能通过最大RevisionNumber替代Head推导；Head不复制RevisionNumber、正文、ProjectId或并发版本。

## Aggregate不变量

`StoryBibleAggregate`只组合一个稳定对象、Head和当前Revision，不嵌入完整历史。构造时必须同时满足：

1. Head和当前Revision都属于同一StoryBible；
2. Head指向当前Revision的精确ID；
3. ConcurrencyVersion数值等于当前RevisionNumber；
4. StoryBible、Head和当前Revision的当前时间完全一致；
5. StoryBible创建时间不晚于当前更新时间；
6. 当前Revision不早于StoryBible创建时间；
7. 所有组件和字段均为精确领域类型且时间为aware UTC。

任何损坏组合抛出固定、安全的`InvalidStoryBibleState`，不回显标题或正文。

## 纯转换

`create_initial_story_bible()`只使用调用方提供的StoryBible ID、Revision ID、ProjectId、标题、正文和时间。它不生成ID、不调用Clock、不访问Project或数据库，固定创建RevisionNumber 1和ConcurrencyVersion 1；StoryBible的创建/更新时间、Revision创建时间及Head更新时间为同一规范UTC时刻。

`append_story_bible_revision()`先精确验证Aggregate，再以通用`assert_expected_version()`比较expected和actual版本。stale时抛出带安全整数`expected_version`和`actual_version`的`ConcurrencyConflict`；该检查优先于时钟回退、新Revision ID重复和后续构造。

并发检查通过后，`now`可以等于当前更新时间，但不能更早；新Revision ID不能等于当前Revision ID。成功时RevisionNumber和ConcurrencyVersion各递增1，StoryBible ID、ProjectId和创建时间保持不变，更新时间、Head和当前Revision切换到调用方提供的新完整快照。

完整替换语义固定为：

```text
新title + 新content = 新Revision完整正文
```

空content是明确的完整替换。转换不支持`None`保留旧值、缺字段、Patch、字段merge、自动合并、自动重试或从旧Revision补齐内容；旧Aggregate、旧Revision和旧Head保持不变。

## 错误隐私与不可变性

Story Bible错误只包含固定公开消息，不保存HTTP状态、API码、SQL、路径、对象`repr`或用户正文。标识错误复用`InvalidDomainIdentifier`，并发错误复用`ConcurrencyConflict`，时间和组合状态以安全的领域状态错误拒绝。自动测试使用`STORY_BIBLE_SECRET_CANARY`确认异常、架构诊断和质量门输出不会泄漏正文。

所有实体和值对象均为`frozen=True, slots=True`或现有不可变Prefixed ULID类型，没有实例`__dict__`、setter、可变容器、`update_in_place`或删除Revision方法。追加转换返回全新对象，不修改任何旧对象。

## DEV-2.2持久化适配

DEV-2.2没有改变上述领域对象和值规则。纯Python Repository契约属于Story Bible公开领域边界，具体SQLAlchemy Record、Mapper、查询和事务Repository隔离在`story_bible.persistence`；领域文件不导入持久化实现或SQLAlchemy。

迁移`0003_create_story_bible_foundation`把稳定对象、不可变完整Revision和权威Head分别保存为三表。数据库持久化必须重新应用领域不变量，通过显式Head读取当前Aggregate，并以Stable Object与Head双CAS追加；详细Schema、事务顺序、失败回滚和损坏策略见[Story Bible持久化基础](STORY_BIBLE_PERSISTENCE.md)。

## 当前明确不存在

当前仍没有Story Bible应用命令/查询服务、DTO、HTTP API、OpenAPI路径、前端页面、功能真实性ID、历史读取/回滚/恢复/Diff、Character、World、PowerSystem、Codex生成、Agent、审批或三区能力。三表和Repository只属于内部持久化基础，不能视为用户功能完成。

DEV-2.3只有在独立任务明确授权后才能定义应用层；DEV-2.2不提前实现或授权这些能力。
