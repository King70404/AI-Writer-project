# Project列表读取

DEV-1.6在现有Project当前聚合能力之上增加只读列表链路：应用读取模型与端口、SQLAlchemy单查询适配器、稳定Keyset分页、严格HTTP游标以及`GET /api/v1/projects`。DEV-1.7的`/projects`页面消费该摘要，不改变数据库Schema，也不提供历史、搜索、筛选或自定义排序。

## 应用读取模型与边界

`ProjectListItem`是脱离ORM和Session的不可变摘要，字段精确为：

- `project_id`；
- `current_revision_id`；
- `revision_number`；
- `concurrency_version`；
- `title`；
- `created_at`；
- `updated_at`；
- `revision_created_at`。

列表不返回`description`。简介最大可达2000字符，列表只需要识别Project及显示当前标题；完整简介继续由单Project GET读取，避免响应体积随页大小放大。

`ProjectListPosition`只保存最后一个已返回Project的aware UTC `created_at`和规范`project_id`。`ListProjectsQuery`只保存`limit`与可选`after`，默认limit为20，合法范围为1至100；bool、浮点、字符串和越界值不会在应用边界被当作整数。`ProjectListPage`保存tuple items、可选next position和bool `has_more`：只有确有下一页时才以最后一个实际返回item建立next position；最终页与空页都没有next position，空页固定返回空tuple。

专用`ProjectListReader`端口位于Project应用边界，不扩展写Repository，也不建立通用ReadRepository、Pagination或CQRS框架。`ProjectListQueryService`只验证一个`ListProjectsQuery`并调用Reader一次，不执行单Project N次读取、预取、缓存、写入、时钟或ID生成。

## 固定排序与Keyset条件

排序不可由客户端改变，固定为：

```text
projects.created_at DESC
projects.id DESC
```

`created_at`是稳定Project的不可变创建时间，Project ID是相同时间下的确定性并列键。不能用`updated_at`或当前Revision时间分页：Project修订会改变这些时间，使Project跨页移动并产生重复或遗漏；标题同样不是稳定排序键。

存在position时，查询条件固定为：

```sql
projects.created_at < :after_created_at
OR (
    projects.created_at = :after_created_at
    AND projects.id < :after_project_id
)
```

条件与降序方向一致且使用严格小于，不会重复上一页最后一项。实现不使用OFFSET，因为越靠后的OFFSET需要跳过更多记录，且页间插入会改变行偏移。接口也不执行COUNT或返回total、total pages和page number；这些值会增加额外全表工作且不是继续Keyset遍历所必需。

## 单查询实现与数据完整性

`SqlAlchemyProjectListReader`每次调用创建并关闭独立Session，使用普通只读事务和一条业务SELECT：

```text
projects
LEFT JOIN project_heads
LEFT JOIN project_revisions
```

查询只选择摘要与完整性检查所需列，不选择description或历史Revision，不执行N+1、COUNT、OFFSET或写SQL。它请求`limit + 1`行判断`has_more`，实际最多返回limit项；lookahead行不会进入items，也不会成为next position。

LEFT JOIN用于发现而不是隐藏损坏状态。缺少Head、当前Revision缺失、所有权不一致、非法ID/版本/修订号/时间/标题或非法时间关系都会让整页抛出安全`ProjectDataCorruption`；Reader不跳过、部分返回、猜测、删除或修复数据。数据库或Schema不可用转换为`ProjectRepositoryError`。未迁移数据库因此返回HTTP 503 `PROJECT_PERSISTENCE_UNAVAILABLE`，不会伪装为空列表，也不会自动建表或迁移。

## HTTP游标

Web游标是版本化、确定性、URL安全且无填充的Base64编码。UTF-8 JSON载荷字段精确为：

```json
{
  "v": 1,
  "created_at": "RFC3339 UTC时间",
  "project_id": "prj_..."
}
```

编码使用排序键、紧凑分隔符和规范UTC时间，结果不含`=`、`+`或`/`。游标不包含标题、简介、Revision ID、并发版本、SQL、路径或秘密。它只是opaque传输位置，不是加密值、签名、安全令牌、授权信息或数据库事务快照，服务端不会信任它提供列名、排序方向或SQL。

解码限制为最多512个ASCII字符，并拒绝空值、非Base64url、外部填充、无效UTF-8/JSON、数组或标量、重复键、缺失或额外字段、非整数版本1、非字符串值、naive或非UTC时间、非规范Project ID及控制字符。解码后必须重新规范编码并与输入逐字相等，因此等价但非规范的表示同样失败。失败固定返回HTTP 400 `INVALID_CURSOR`，不回显输入，也不会调用列表服务。

## HTTP响应与页间变化

`GET /api/v1/projects`接受可选`limit`和`cursor`，按“验证limit、解析cursor、构造查询、调用服务一次、显式映射DTO”的顺序执行。它不要求本地Session、Origin或CSRF，但继续受Host验证和安全响应头保护，响应使用`Cache-Control: no-store`，不返回ETag或Location。

同一静态数据集完整遍历不会重复或遗漏。取得旧cursor后新创建的Project位于该position之前，不会进入旧cursor的后续页；重新请求第一页时，新Project位于前部。Project修订不改变不可变创建时间，所以分页位置不变，但尚未读取项在后续请求中会反映当时的当前Revision标题、版本和Revision ID。多个HTTP请求之间没有数据库快照隔离，cursor也不承诺把页面内容冻结在第一次请求时刻。

当前接口不支持search、filter、sort、total或历史。`/projects`以前端固定`limit=20`读取第一页，并把`next_cursor`作为不透明值经`URLSearchParams`传回；前端不解析、不修改、不持久化cursor，加载失败保留现有items和cursor。列表仍不显示description。完整UI范围见[Project前端列表与创建流程](PROJECT_FRONTEND.md)。
