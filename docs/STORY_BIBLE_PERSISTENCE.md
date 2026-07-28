# Story Bible 持久化基础

本文档记录 DEV-2.2 建立的内部持久化边界。它把 DEV-2.1 的纯领域 Aggregate 保存为 SQLite 三表；DEV-2.3只在其公开Repository契约之上增加应用用例，没有改变本文件的Schema、事务或错误语义。

## 三表职责

`story_bibles`保存稳定对象：`id`、唯一`project_id`、`concurrency_version`、`created_at`和`updated_at`。它不保存标题、正文或当前 Revision ID。

`story_bible_revisions`保存不可变完整快照：`id`、`story_bible_id`、正数`revision_number`、1至120代码点且非空白的`title`、最多50000代码点且允许空字符串的`content`和`created_at`。它没有更新时间、并发版本、Project ID副本、Diff或父Revision ID。

`story_bible_heads`只保存`story_bible_id`、当前`revision_id`和`updated_at`。Head是当前快照的权威指针，不复制RevisionNumber、标题、正文、Project ID或ConcurrencyVersion。

## Project归属

一个Project至多拥有一个Story Bible。`story_bibles.project_id`具有唯一约束和指向`projects.id`的RESTRICT外键；创建前Repository只读取Project是否存在，不修改Project表，也不调用Project Repository。缺失归属以固定、安全的`StoryBibleProjectNotFound`报告。

跨模块读取仅限Project ID归属检查。Story Bible持久化不得写`projects`、`project_revisions`或`project_heads`，Project模块也不得直接写Story Bible三表。

## 归属和不可变性约束

Head既外键指向稳定StoryBible，也以`(story_bible_id, revision_id)`复合外键指向`story_bible_revisions(story_bible_id, id)`，因此不能指向其他StoryBible的Revision。Revision拥有`(story_bible_id, revision_number)`和`(story_bible_id, id)`两个唯一约束。

迁移建立固定触发器`trg_story_bible_revisions_no_update`和`trg_story_bible_revisions_no_delete`。任何直接SQL或ORM UPDATE/DELETE都以固定消息拒绝；Repository只能追加完整Revision。

不能用“最大RevisionNumber”推导当前Revision：并发失败或损坏状态可能让“最大值”和已提交Head语义分离。读取必须通过显式Head及其复合所有权约束恢复当前Aggregate。

## ORM和Mapper

三个SQLAlchemy Record只表达已授权列、键和约束，不建立relationship或级联写入。`StoryBibleRevisionRecord.__repr__`不包含标题或正文。

Mapper逐字段执行领域对象与Record之间的显式转换，不使用反射、`asdict`或Pydantic。读回时重新应用所有领域不变量；错误类型、损坏标识、所有权、版本或时间组合统一映射为`StoryBibleDataCorruption`，且返回的Aggregate不依赖存活Session。

## Repository契约

纯Python `StoryBibleRepository` Protocol定义：

- `create(aggregate)`；
- `get(story_bible_id)`；
- `get_for_project(project_id)`；
- `append_revision(story_bible_id, *, expected_version, title, content, clock, revision_id_factory)`。

具体`SqlAlchemyStoryBibleRepository`是外向适配器。构造函数只接收可调用的Session工厂；每次方法调用创建并关闭一个独立Session，不拥有全局Session或通用Unit of Work。

`get()`使用一条固定JOIN读取稳定对象、Head和当前Revision；不存在时返回`None`。`get_for_project()`同样使用一条固定查询：Project不存在抛出`StoryBibleProjectNotFound`，Project存在但尚无StoryBible返回`None`。

## 创建事务

`create()`在一个`BEGIN IMMEDIATE`事务内依次验证归属Project、StoryBible ID和Project唯一基数，再写稳定对象、Revision 1和Head。三个flush和最终commit属于同一原子事务；任何Revision、Head、约束、Session或commit失败都完整rollback，不保留部分行。

## 追加事务和双CAS

`append_revision()`固定顺序为：

1. 在打开Session前验证参数；
2. `BEGIN IMMEDIATE`；
3. 通过Head读取当前Aggregate；
4. 检查StoryBible存在；
5. 比较expected与actual ConcurrencyVersion；
6. 调用Clock一次；
7. 调用Revision ID factory一次；
8. 执行DEV-2.1纯追加转换；
9. INSERT完整新Revision；
10. Stable Object以`id + expected concurrency_version`执行CAS；
11. Head以`story_bible_id + 旧revision_id`执行CAS；
12. 单次commit。

Stable CAS只推进ConcurrencyVersion和更新时间。Head CAS只推进Revision ID和更新时间。任一CAS未精确更新一行时先rollback：稳定对象CAS miss安全解析为不存在或并发冲突，Head CAS miss解析为不存在或数据损坏；新Revision和已发生的指针修改均不得残留。

stale和不存在检查均先于Clock和Revision ID factory，因此二者调用数为0且数据库无写入。成功路径严格各调用一次。Clock或ID factory抛错时，后续副作用不发生，整个事务回滚并返回固定持久化错误。

SQLite写事务使用`BEGIN IMMEDIATE`串行化锁获取，使两个独立Repository实例同时以expected version 1追加时确定地产生一个成功和一个`ConcurrencyConflict`，而不是两个成功或向调用方泄漏`database is locked`。

## 损坏与错误隐私

读取不修复、不猜测、不以最大RevisionNumber绕过Head。缺Head、缺Revision、跨所有者指针、非法值、版本不一致或时间不一致都使整个读取失败并抛出`StoryBibleDataCorruption`。

所有Repository错误只公开固定消息及必要的规范ID或并发整数。异常字符串、Record `repr`、SQL、数据库路径、title、content、token和内部异常正文不得进入公开消息或测试日志；底层异常只作为异常链保留。

## Migration 0003

`0003_create_story_bible_foundation`以`0002_create_project_foundation`为唯一父迁移，建立三表、全部外键/唯一/检查约束和两个不可变触发器。downgrade按触发器、Head、Revision、Stable Object的逆依赖顺序删除StoryBible结构，保留三张Project表和0002版本状态；重新upgrade可得到相同空结构。

正式`Base.metadata`在明确调用模型注册入口后精确包含三张Project表和三张StoryBible表。普通`import aiwebnovel.story_bible`仍不注册ORM、不连接数据库、不执行迁移。

## 应用与HTTP调用边界

DEV-2.3的命令服务创建时调用`create()`一次，修订时调用`append_revision()`一次且不预先GET；应用层把同一Clock与Revision ID Factory传给Repository，因此本文件定义的事务内stale优先级保持不变。查询服务分别只调用`get()`或`get_for_project()`一次，Project不存在错误原样传播，Project存在但无Story Bible由应用边界转换为专用错误。

DEV-2.4的FastAPI lifespan复用现有Engine和Session factory装配本Repository，四条HTTP操作仍只通过DEV-2.3应用服务进入事务边界。应用启动和请求都不会创建表或执行迁移；空库或0002数据库的合法Story Bible调用返回安全503。HTTP层不改变三表、双不可变触发器、stale优先级或Repository调用次数。

DEV-2.5已增加调用现有HTTP边界的纯文本前端路由与页面，但没有改变本文件的三表或Repository语义。当前仍没有Revision历史读取API、Character、World、PowerSystem、Planning、Codex、Agent、审批、分支、导出或备份。传输契约见[Story Bible HTTP API](STORY_BIBLE_HTTP_API.md)，界面契约见[Story Bible前端流程](STORY_BIBLE_FRONTEND.md)。
