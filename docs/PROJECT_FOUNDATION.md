# Project持久化基础

DEV-1.2建立Project模块的内部领域与持久化基础；DEV-1.3在不改变Schema的前提下增加内部事务Repository。当前仍不提供应用Service、API、DTO或前端项目管理功能。应用启动不会自动执行迁移，也不会创建默认Project或示例数据。

## 所有权与对象关系

Project模块唯一拥有`projects`、`project_revisions`和`project_heads`。其他模块未来只能通过Project公开应用契约访问这些数据，不得直接写表；本任务尚未创建该跨模块访问接口。

`Project`是稳定身份和乐观并发锚点，只包含`ProjectId`、`ConcurrencyVersion`以及创建、更新时间，不复制标题和简介。`ProjectRevision`保存不可变的标题与简介修订，包含独立`ProjectRevisionId`、所属Project、`RevisionNumber`和创建时间，不含`updated_at`、并发版本或“当前”布尔值。`ProjectHead`是独立的当前修订指针；它只保存Project、Revision和更新时间，不复制修订内容。只读`ProjectAggregate`组合三者并重新验证所有权、指针和时间顺序，不保存历史列表，也不执行查询。

正式业务ID由Project模块通过通用前缀ULID工厂声明：

- `ProjectId`固定前缀为`prj`；
- `ProjectRevisionId`固定前缀为`prv`。

两个类型不可互换，不建立全局前缀注册表。`RevisionNumber`表示同一Project内从1开始的人类可理解修订顺序；`ConcurrencyVersion`表示稳定Project行的乐观并发版本。两者职责不同，不能混用。

## 纯领域转换

初始创建转换只读取一次注入时钟，生成一个Project ID和一个Revision ID，建立修订号1、并发版本1的Project、Revision和Head；三者使用同一aware UTC时间。默认ID来源是DEV-1.1的密码学安全进程内ULID生成器，测试可以注入确定性工厂。转换不访问数据库、目录、日志或事件系统。

下一修订转换首先验证调用方的预期`ConcurrencyVersion`；stale版本立即抛出通用`ConcurrencyConflict`，不会调用时钟或ID工厂。成功时追加新的不可变Revision，递增修订号与Project并发版本，并让Head指向新Revision；旧Aggregate和旧Revision不变。

本模块固定采用“明确拒绝时钟回退”策略：新时刻如果早于Project当前`updated_at`、当前Revision的`created_at`或Head的`updated_at`，转换抛出安全的Project领域错误，不写入更早业务时间，不自动钳制、重试或合并。

## 三表结构

`projects`保存稳定ID、正数并发版本和aware UTC创建、更新时间，不含标题、简介、删除状态、用户或Codex字段。

`project_revisions`保存修订ID、所属Project、正数修订号、标题、简介和创建时间。`(project_id, revision_number)`唯一；`(project_id, id)`也唯一，供Head复合外键引用。标题数据库长度为1至120且不能是空白文本，简介最大2000字符。表不含`updated_at`、`is_current`、并发版本或JSON metadata。

`project_heads`以`project_id`为主键，因此一个Project最多一个Head。`(project_id, revision_id)`复合外键引用`project_revisions(project_id, id)`，阻止Head指向其他Project的Revision。

当前修订使用独立Head表，而不是`ProjectRevision.is_current`，因为Revision必须保持真正不可变，Revision追加与指针替换也应职责分离。后续Repository可以在同一事务内插入Revision、比较并更新Project并发版本、更新Head，而无需修改旧Revision。

## 数据库不可变性与时间

迁移`0002_create_project_foundation`创建三表、约束、索引以及两个SQLite触发器：

- `trg_project_revisions_no_update`拒绝任何Revision UPDATE；
- `trg_project_revisions_no_delete`拒绝任何Revision DELETE。

触发器是数据库级保护，不由ORM事件监听器替代；INSERT仍然允许。降级先删除触发器，再按外键顺序删除Head、Revision和Project表。迁移只建立结构，不插入用户Project或示例数据，也不会被应用启动自动执行。

通用`UtcDateTimeType`只接受aware datetime，绑定前规范为UTC；SQLite读取的UTC值恢复为aware UTC，不依赖系统本地时区。它不包含Project业务规则。

## Repository事务边界

SQLite约束可以保证正数版本、修订号唯一、Head唯一、Head与Revision同属一个Project以及Revision不可更新或删除，但数据库无法单独保证每个已提交Project始终存在Head。DEV-1.3的Repository已在同一`BEGIN IMMEDIATE`事务中原子完成Project/Revision/Head初始插入；追加修订执行：

1. 插入新Revision；
2. 以`WHERE id = :project_id AND concurrency_version = :expected_version`比较并更新Project；
3. 以旧Revision ID为条件更新Head；
4. 任一CAS影响行数不是1时回滚，并通过事后安全读取转换为缺失、stale或持久化冲突。

Repository的公开契约保持纯Python，SQLAlchemy实现位于Project持久化层；每次操作使用独立Session。`get()`以单条业务SELECT恢复一致当前聚合并拒绝损坏状态，完整事务、CAS、错误与并发规则见[Project Repository事务边界](PROJECT_REPOSITORY.md)。当前没有应用Service、API、DTO、前端项目列表，也没有历史查询、删除、归档、恢复、正式区、候选区、分支、审批、Character、Chapter、Codex、Agent或工作流。
