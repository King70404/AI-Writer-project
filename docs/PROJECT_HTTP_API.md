# Project HTTP API

DEV-1.5在Project应用用例之上提供三个最小HTTP接口。它只暴露单个Project的创建、当前状态读取和完整修订，不提供列表、历史、删除、归档、PATCH或前端Project页面。

## 接口与DTO

| 方法与路径 | 成功状态 | 语义 |
| --- | ---: | --- |
| `POST /api/v1/projects` | 201 | 创建稳定Project、初始不可变Revision和Head，返回当前快照、相对`Location`与强ETag |
| `GET /api/v1/projects/{project_id}` | 200 | 只读取Head指向的当前快照，返回强ETag，不加载修订历史 |
| `PUT /api/v1/projects/{project_id}` | 200 | 用完整标题和简介创建下一不可变Revision，CAS成功后返回新快照与新ETag |

`CreateProjectRequest`和`ReviseProjectRequest`都只接受`title: str`与默认值为`""`的`description: str`。模型使用Pydantic v2严格类型、`extra="forbid"`和冻结配置；数字不转字符串、`null`不转空串，也不能提交ID、版本、时间、metadata或安全字段。DTO不修剪或改写文本，最终标题、简介业务验证仍由Project值对象负责。

`ProjectResponse`精确包含`project_id`、`current_revision_id`、`revision_number`、`concurrency_version`、`title`、`description`、`created_at`、`updated_at`、`revision_created_at`和`head_updated_at`。四个时间必须为aware UTC并以RFC 3339序列化；响应不含ORM、Session、Head内部结构或Revision历史。`project_response_from_snapshot()`只逐字段复制应用`ProjectSnapshot`，不访问Repository或数据库。

PUT采用完整替换而不是PATCH，是为了让每个Revision拥有一份完整、可独立解释的标题与简介，并让一次请求只对应一次Repository事务。缺字段不会表示“保持旧值”，正文也不接受expected version。

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

POST和PUT完整继承Host、Origin、本地Session Cookie、`X-CSRF-Token`、JSON内容类型和正文大小限制。Session只能从`GET /api/v1/security/session`获取，CSRF令牌仍只保存在调用方内存。GET不要求Session、Origin或CSRF，但仍经过Host验证并返回安全响应头与`Cache-Control: no-store`。

CORS只允许配置的明确origin，`allow_credentials=false`；方法精确为`GET`、`POST`、`PUT`、`OPTIONS`，不允许PATCH或DELETE。允许Header包括`Content-Type`、`X-CSRF-Token`、`If-Match`和`X-Request-ID`，暴露`X-Request-ID`、`ETag`和`Location`。开发模式仍应由Vite相对`/api`代理调用。

## 装配、迁移与当前限制

`aiwebnovel.main`在应用生命周期内用既有Session工厂显式装配：

```text
session_factory
→ SqlAlchemyProjectRepository
→ ProjectCommandService / ProjectQueryService
→ app.state Project服务引用
```

`project.web`不导入SQLAlchemy、ORM模型、具体Repository或Session。应用构造与Router导入不连接数据库；关闭时清除服务引用。应用绝不自动运行Alembic，Project Schema必须由操作者对目标数据库显式升级到`0002_create_project_foundation`。未迁移数据库调用Project接口会安全返回503，不会自动建表或伪装成404，live仍可响应。

当前没有Project列表、修订历史、删除、归档、恢复、PATCH、自动保存或前端Project页面。DEV-1.6必须另行授权；本文件不预先定义其业务实现。
