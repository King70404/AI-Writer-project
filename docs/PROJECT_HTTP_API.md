# Project HTTP API

DEV-1.5在Project应用用例之上提供创建、单个当前状态读取和完整修订；DEV-1.6另增加当前Revision摘要列表。当前共四个Project HTTP接口，不提供历史、删除、归档或PATCH；DEV-1.7的`/projects`前端调用列表GET和创建POST，DEV-1.8的`/projects/:projectId`前端调用当前详情GET与完整修订PUT。

## 接口与DTO

| 方法与路径 | 成功状态 | 语义 |
| --- | ---: | --- |
| `GET /api/v1/projects` | 200 | 按`created_at DESC, project_id DESC`返回当前Revision摘要，使用严格Keyset cursor，不返回description或total |
| `POST /api/v1/projects` | 201 | 创建稳定Project、初始不可变Revision和Head，返回当前快照、相对`Location`与强ETag |
| `GET /api/v1/projects/{project_id}` | 200 | 只读取Head指向的当前快照，返回强ETag，不加载修订历史 |
| `PUT /api/v1/projects/{project_id}` | 200 | 用完整标题和简介创建下一不可变Revision，CAS成功后返回新快照与新ETag |

`CreateProjectRequest`和`ReviseProjectRequest`都只接受`title: str`与默认值为`""`的`description: str`。模型使用Pydantic v2严格类型、`extra="forbid"`和冻结配置；数字不转字符串、`null`不转空串，也不能提交ID、版本、时间、metadata或安全字段。DTO不修剪或改写文本，最终标题、简介业务验证仍由Project值对象负责。

`ProjectResponse`精确包含`project_id`、`current_revision_id`、`revision_number`、`concurrency_version`、`title`、`description`、`created_at`、`updated_at`、`revision_created_at`和`head_updated_at`。四个时间必须为aware UTC并以RFC 3339序列化；响应不含ORM、Session、Head内部结构或Revision历史。`project_response_from_snapshot()`只逐字段复制应用`ProjectSnapshot`，不访问Repository或数据库。

PUT采用完整替换而不是PATCH，是为了让每个Revision拥有一份完整、可独立解释的标题与简介，并让一次请求只对应一次Repository事务。缺字段不会表示“保持旧值”，正文也不接受expected version。

列表响应使用`ProjectListItemResponse`和`ProjectListResponse`。Item字段精确为Project ID、当前Revision ID、RevisionNumber、ConcurrencyVersion、title以及Project创建/更新时间与Revision创建时间；不含description。Page字段精确为`items`、`next_cursor`和`has_more`，不含total、page或offset。limit默认20、合法范围1至100；非法limit返回422 `REQUEST_VALIDATION_ERROR`，非法cursor返回400 `INVALID_CURSOR`，且两者都不会调用列表服务。

列表cursor是版本1、规范JSON的无填充Base64url编码，只表达不可变`created_at + project_id`位置。它不是授权、安全令牌或跨请求数据库快照；严格解码拒绝重复键、额外字段、非UTC时间和非规范编码，不回显输入。Project修订不会改变分页位置；页间新建Project不会进入旧cursor后续页，但会位于新的第一页。完整语义见[Project列表读取](PROJECT_LISTING.md)。

## ETag与并发前提

成功的POST、GET、PUT都返回格式为`"<concurrency_version>"`的强ETag，例如`"1"`。ETag只表达当前`ConcurrencyVersion`，不包含正文、Project ID或Revision ID。

PUT必须携带恰好一个规范Header：

```http
If-Match: "1"
```

缺失Header返回428 `PRECONDITION_REQUIRED`；无引号、弱ETag、`*`、列表、0、负数、布尔文本或64位溢出返回400 `INVALID_IF_MATCH`；格式合法但版本已过期由Repository CAS裁决并返回412 `PROJECT_VERSION_CONFLICT`，details只含`expected_version`和`actual_version`。服务不会预读、自动重试、合并或覆盖新版本。

## 错误与隐私

接口复用全局`AppError`结构和request ID。固定映射如下：

| 来源 | HTTP | 错误码 |
| --- | ---: | --- |
| Pydantic请求结构失败 | 422 | `REQUEST_VALIDATION_ERROR` |
| 列表limit失败 | 422 | `REQUEST_VALIDATION_ERROR` |
| 列表cursor失败 | 400 | `INVALID_CURSOR` |
| Project ID非法 | 422 | `INVALID_PROJECT_ID` |
| 标题非法 | 422 | `INVALID_PROJECT_TITLE` |
| 简介非法 | 422 | `INVALID_PROJECT_DESCRIPTION` |
| Project不存在 | 404 | `PROJECT_NOT_FOUND` |
| Project已存在 | 409 | `PROJECT_ALREADY_EXISTS` |
| 并发版本冲突 | 412 | `PROJECT_VERSION_CONFLICT` |
| 存储状态损坏 | 500 | `PROJECT_DATA_CORRUPTION` |
| Repository不可用 | 503 | `PROJECT_PERSISTENCE_UNAVAILABLE` |
| 应用服务未装配 | 503 | `PROJECT_SERVICE_UNAVAILABLE` |

Pydantic 422只返回安全的`field`、`type`和固定`message`，删除原始`input`与`ctx`，不回显标题、简介或完整正文。Project错误映射不返回SQL、数据库路径、异常文本、堆栈、Cookie、Session或CSRF；未知异常继续由全局500处理。

## 安全与CORS

POST和PUT完整继承Host、Origin、本地Session Cookie、`X-CSRF-Token`、JSON内容类型和正文大小限制。Session只能从`GET /api/v1/security/session`获取，CSRF令牌仍只保存在调用方内存。详情与列表GET都不要求Session、Origin或CSRF，但仍经过Host验证并返回安全响应头与`Cache-Control: no-store`；列表不返回ETag或Location。

CORS只允许配置的明确origin，`allow_credentials=false`；方法精确为`GET`、`POST`、`PUT`、`OPTIONS`，不允许PATCH或DELETE。允许Header包括`Content-Type`、`X-CSRF-Token`、`If-Match`和`X-Request-ID`，暴露`X-Request-ID`、`ETag`和`Location`。开发模式仍应由Vite相对`/api`代理调用。

## 装配、迁移与当前限制

`aiwebnovel.main`在应用生命周期内用既有Session工厂显式装配：

```text
session_factory
→ SqlAlchemyProjectRepository
→ ProjectCommandService / ProjectQueryService
→ SqlAlchemyProjectListReader / ProjectListQueryService
→ app.state Project服务引用
```

`project.web`不导入SQLAlchemy、ORM模型、具体Repository或Session。应用构造与Router导入不连接数据库；关闭时清除服务引用。应用绝不自动运行Alembic，Project Schema必须由操作者对目标数据库显式升级到`0002_create_project_foundation`。未迁移数据库调用Project接口会安全返回503，不会自动建表或伪装成404，live仍可响应。

当前没有修订历史、删除、归档、恢复、PATCH、自动保存、搜索、筛选或自定义排序。`/projects`提供列表、加载更多和创建；`/projects/:projectId`提供当前详情、完整替换编辑与显式412恢复。前端严格验证强ETag与正文版本一致，PUT不自动重试或合并。列表边界见[Project前端流程](PROJECT_FRONTEND.md)，详情并发语义见[Project详情与修订前端流程](PROJECT_DETAIL_FRONTEND.md)。
