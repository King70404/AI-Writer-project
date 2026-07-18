# 领域基础原语

DEV-1.1建立阶段1可复用的内部领域原语。它不是Project模块，不创建业务实体、业务表、Repository、API或用户页面，也不增加任何用户可见功能。

## 纯Python边界

`aiwebnovel.domain`只依赖Python标准库，不导入FastAPI、Pydantic、SQLAlchemy或其他应用基础设施。这样，标识、时间、修订与并发规则可以在HTTP、数据库和进程启动方式之外独立验证。SQLAlchemy转换属于外向适配器，位于`aiwebnovel.db.types`；依赖方向只能由`db`指向`domain`。

## ULID

`Ulid`表示标准128位ULID：高48位是UTC Unix毫秒时间戳，低80位是随机部分。规范文本固定为26个大写Crockford Base32字符，字母表为：

```text
0123456789ABCDEFGHJKMNPQRSTVWXYZ
```

解析可以接受小写，但输出总是大写；`I`、`L`、`O`、`U`、空白、控制字符、分隔符、错误长度和超出128位范围的值都会被拒绝。对象不可变，可安全用于相等、哈希、总排序、整数往返、毫秒时间戳和UTC时间转换。

ULID中的时间只用于大致排序和分区辅助，不是业务事件的可信审计时钟。系统时钟可能调整，生成器也会在回退时沿用上一毫秒；需要审计的业务事实必须使用独立、明确的UTC时间字段和来源证据。完整48位时间戳可以作为整数保存，但超出Python `datetime`可表示年份时，UTC datetime转换会明确失败。

## 进程内单调生成

`MonotonicUlidGenerator`在一个进程内使用锁保护状态。新毫秒从密码学安全随机80位值开始，同一毫秒或系统时钟回退时递增上一随机值，因此生成结果严格递增且不会回绕。80位空间耗尽时明确失败，不覆盖旧值。默认全局生成器由`new_ulid()`复用；测试可注入时钟和随机源，但测试源不会替换生产全局状态。

该保证不跨进程持久化，应用重启后也不承诺与旧进程严格单调。不同进程之间依靠80位密码学随机空间维持低碰撞概率。

## 前缀标识

`PrefixedUlid`的规范格式是：

```text
prefix_01ARZ3NDEKTSV4RRFFQ69G5FAV
```

前缀长度为2至12，只能以小写字母开头，后续只能是小写字母或数字；分隔符固定为一个下划线，额外下划线、大写、空白和保留前缀`admin`、`api`、`root`、`sys`、`system`会被拒绝。排序只先比较前缀、再比较ULID；前缀和ULID都相同时属于排序并列项。不同前缀或不同实际具体类型的实例不是同一标识，即使两次类型声明使用相同名称和前缀也不会相等。

`create_prefixed_ulid_type()`用于由所属业务模块声明固定前缀的不可变具体类型，并提供`new()`、`parse()`和`from_ulid()`；固定前缀由类型工厂的闭包保存，修改同名类属性不能改变它。工厂及这些类方法都以`type[PrefixedUlid]`、`Self`等静态类型声明供mypy检查，不使用`Any`扩散。由于具体类在运行时创建，调用方应把工厂结果标注为`type[PrefixedUlid]`，把值标注为`PrefixedUlid`，不能把运行时变量误当作静态类型别名：

```python
identifier_type: type[PrefixedUlid] = create_prefixed_ulid_type("TstId", "tst")
identifier: PrefixedUlid = identifier_type.from_ulid(ulid)
```

本任务没有建立业务前缀注册表，也没有定义Project、Chapter或其他真实业务ID；下一业务模块必须在自己的模块内选择、记录并测试其前缀，不能在领域基础层提前登记。

## UTC领域时间

`utc_now()`、`ensure_utc()`、`datetime_to_milliseconds()`和`milliseconds_to_datetime()`统一返回或处理timezone-aware UTC时间。naive datetime会被拒绝；其他时区的aware值会规范化为UTC。datetime转毫秒时明确截断毫秒以下精度，不依赖系统本地时区，支持范围与ULID的48位毫秒时间戳一致。

## 修订号与并发版本

`RevisionNumber`表示同一稳定对象的不可变修订序列，第一版为1。它用于人类和业务规则可理解的版本顺序，不是数据库行版本，也不是Git提交号。

`ConcurrencyVersion`表示乐观并发控制中的行版本，新稳定对象从1开始。`assert_expected_version()`要求实际版本与调用方预期版本一致；不一致时抛出`ConcurrencyConflict`，提供安全的`expected_version`和`actual_version`结构化字段。冲突不会自动覆盖、自动重试或修改实际版本。

两者是不同的不可变类型，都只接受1至64位有符号整数上限之间的真正整数，拒绝`bool`、浮点数、字符串和另一种版本类型。`next()`返回新实例，达到上限后明确失败，不能回绕。后续代码不得把修订顺序与并发写保护混用。

## SQLAlchemy适配器

`aiwebnovel.db.types`负责在领域值与数据库标量之间转换：

- `UlidType`：固定26字符TEXT；
- `PrefixedUlidType`：最长39字符TEXT；
- `RevisionNumberType`：INTEGER；
- `ConcurrencyVersionType`：INTEGER。

适配器在绑定时要求正确领域类型，在读取时恢复领域对象，并对污染值明确失败。它们不创建表；测试使用独立`MetaData`和临时SQLite数据库，正式`Base.metadata`仍为空，Alembic head保持不变。

## 依赖和序列化规则

- `domain`只导入标准库或自己的子模块；
- `domain`不得导入`core`、`db`、`storage`、`security`、`web`、`diagnostics`或`main`；
- `domain`不得导入FastAPI、Pydantic或SQLAlchemy；
- `db`可以导入公开领域类型，反向依赖禁止；
- 生产源码不得从测试目录取得前缀、时钟或随机源；
- 文本和整数转换必须显式完成，不安装全局JSON编码补丁，也不修改FastAPI编码行为。

四种领域值都使用无`__dict__`的不可变`slots`对象，不是dataclass；常见Web编码器不能自动展开内部状态。边界DTO必须显式调用`str()`或`int()`，不能依赖隐式对象编码。
