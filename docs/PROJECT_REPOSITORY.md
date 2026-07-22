# Project Repository事务边界

DEV-1.3在Project数据所有者内部建立纯Python Repository契约和SQLAlchemy SQLite适配器。它只提供内部原子创建、当前聚合读取和不可变修订追加；当前仍没有Project应用Service、API、DTO、历史查询、删除语义或前端项目管理功能。

## 公开契约与所有权

`aiwebnovel.project.repository.ProjectRepository`只声明：

- `create(ProjectAggregate) -> ProjectAggregate`；
- `get(ProjectId) -> ProjectAggregate | None`；
- `append_revision(ProjectId, ConcurrencyVersion, ProjectTitle, ProjectDescription, ...) -> ProjectAggregate`。

契约只依赖Python标准库、Project领域类型和通用domain类型，不导入SQLAlchemy、FastAPI或Pydantic，不接受裸字符串ID或裸整数并发版本，也不返回Session、ORM Record、字典或惰性加载对象。

Repository位于Project内部，因为Project唯一拥有`projects`、`project_revisions`和`project_heads`的数据语义与事务不变量。项目不建立通用CRUD Repository：`save(any_entity)`会掩盖Revision只追加、双CAS和三表原子性，也会为跨模块任意SQL或跨所有者事务留下入口。

## SQLAlchemy实现与Session生命周期

`aiwebnovel.project.persistence.repository.SqlAlchemyProjectRepository`是Project持久化层的同步SQLAlchemy实现。构造只保存`session_factory`，不连接数据库、不运行迁移。每次公开操作创建独立Session；操作之间不复用Session，也不跨线程共享Session。成功写入后提交，任何失败先回滚，所有路径最终关闭Session并归还连接。

写操作成功后采用“返回已验证领域Aggregate”策略：输入创建Aggregate或纯领域转换产生的新Aggregate只有在flush和commit成功后才返回。数据库没有会改写这些领域字段的默认值或触发器，因此不需要返回绑定Session的Record，也不需要为成功结果额外打开读取Session。

## SQLite写事务策略

`create()`和`append_revision()`在任何业务读取或写入前执行`BEGIN IMMEDIATE`。这会取得当前SQLite数据库的写事务，避免两个先读后写事务在锁升级时出现不确定行为；不会使用`BEGIN EXCLUSIVE`，也不会改变普通`get()`的读取策略。锁等待上限继续由现有引擎`busy_timeout`配置决定；Repository不无限等待、不自动重试，也不会把锁错误伪装为成功或业务冲突。

## 原子创建

`create()`在同一立即写事务中按以下顺序执行：

1. 检查稳定Project ID是否已存在；
2. 插入`projects`并flush；
3. 插入第一条`project_revisions`并flush；
4. 插入`project_heads`并flush；
5. commit后返回原领域Aggregate。

重复Project ID转换为`ProjectAlreadyExists`。重复Revision ID或其他非Project主键冲突不会误报Project已存在，而转换为安全持久化冲突。Revision插入或Head插入等晚期失败会回滚此前全部写入，不会留下无Revision的Project或无Head的半聚合。

## 一致读取与损坏检测

`get()`使用一个读取Session和一条固定业务SELECT，从`projects`外连接`project_heads`与当前`project_revisions`，只加载指定Project的当前聚合，不加载修订历史或其他Project，不执行写SQL。Project不存在返回`None`；Session关闭前由现有显式mapper恢复并验证领域Aggregate，因此返回对象可在Session关闭后独立使用。

外连接使Repository能够区分“不存在”与“Project存在但Head或Revision缺失”。读取还会通过类型适配器、mapper和`ProjectAggregate`不变量拒绝：Head缺失、Head目标Revision缺失、Revision所有权不一致、非法Project或Revision领域值、Head时间早于Revision时间，以及Project更新时间早于创建时间。发现这些状态时抛出`ProjectDataCorruption`，不返回部分Aggregate、不猜测当前Revision，也不自动修复、创建Head或删除数据；修复工具属于后续独立任务。

## 原子追加、Project CAS与Head CAS

`append_revision()`在一个立即写事务中执行：

1. 读取一致的当前Aggregate并确认Project存在；
2. 在调用Clock、Revision ID工厂或执行INSERT前验证`expected_version`；
3. 调用纯领域`create_next_project_revision()`；
4. INSERT新Revision；
5. 以`id = project_id AND concurrency_version = expected_version`条件更新Project版本和时间，并要求影响恰好一行；
6. 以`project_id = project_id AND revision_id = expected_current_revision_id`条件更新Head，并要求影响恰好一行；
7. flush、commit并返回新领域Aggregate。

新Revision先插入，使Head只能指向已存在且属于同一Project的Revision；任一步失败由整个事务回滚。旧Revision从不UPDATE或DELETE，0002迁移的不可变触发器继续生效。

Project CAS零行时先回滚，再用新Session安全读取实际状态：Project消失转换为`ProjectNotFound`；Project仍存在转换为通用`ConcurrencyConflict`，其中实际版本来自回滚后的数据库读取，不使用失败事务中的猜测。Head CAS同样是条件更新；零行时完整回滚，并根据事后状态转换为安全缺失或持久化冲突。

stale调用在Clock和ID工厂之前失败，既不生成Revision ID，也不执行任何INSERT或UPDATE。两个独立Repository实例并发使用同一expected版本时，`BEGIN IMMEDIATE`使一个事务完成后另一个读取到新版本：恰好一个成功，另一个得到`ConcurrencyConflict`；Repository不使用全局Python锁、不自动重试、不覆盖、不自动合并。

## 错误与隐私

Project错误层提供`ProjectRepositoryError`、`ProjectAlreadyExists`、`ProjectNotFound`、`ProjectPersistenceConflict`和`ProjectDataCorruption`。stale版本继续使用通用`ConcurrencyConflict`。已知完整性错误只在语义确定时转换为具体错误，未知`IntegrityError`、`OperationalError`、`StatementError`和其他`SQLAlchemyError`转换为安全Repository错误，原异常仅通过异常链供内部诊断。

公开错误文本不包含SQL、SQL参数、数据库文件路径、标题或简介正文。Repository默认不记录业务正文。

## 当前明确不提供

当前Repository不提供修订历史列表、列表、分页、搜索、删除、硬删除、归档、恢复、purge或任意SQL入口。DEV-1.3没有创建通用Unit of Work、应用Service、命令/查询DTO、API或前端页面，也没有改变Schema或新增迁移。DEV-1.4将在独立授权下建立Project应用命令和查询服务；该后续计划不表示相关能力已经实现。
