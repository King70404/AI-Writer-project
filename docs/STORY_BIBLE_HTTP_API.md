# Story Bible HTTP API

DEV-2.4在既有领域、0003三表持久化和应用用例之上增加受控HTTP传输边界。DEV-2.5的`/projects/:projectId/story-bible`页面调用这四条操作，但不改变其协议。当前仍不包含Revision历史API、删除、归档、恢复、Character、World、PowerSystem、规划、Codex或Agent功能。

## 资源与路由

当前精确开放四个端点：

```text
POST /api/v1/projects/{project_id}/story-bible
GET  /api/v1/projects/{project_id}/story-bible
GET  /api/v1/story-bibles/{story_bible_id}
PUT  /api/v1/story-bibles/{story_bible_id}
```

创建和按Project读取使用嵌套路径，因为一个Project至多拥有一个Story Bible，路径直接表达所有权与唯一性；不提供复数集合端点。按稳定ID读取和修订使用Story Bible资源路径，因为这两项操作针对已经建立的独立资源身份。

POST使用不可变`CreateStoryBibleRequest`，字段为必填`title`和默认空字符串的`content`。PUT使用不可变`ReviseStoryBibleRequest`，`title`与`content`均必填并表示完整替换，空`content`是合法的明确替换；不支持PATCH、diff、合并或从旧正文补齐。两个请求均使用Pydantic v2、`strict=True`、`extra="forbid"`和frozen配置，只验证传输结构；领域规范化与业务校验仍由应用层负责。

`StoryBibleResponse`精确复制应用Snapshot的11个原语字段：三个规范ID、RevisionNumber、ConcurrencyVersion、title、content和四个aware UTC时间。两个版本必须是相等的真正正整数，时间关系必须与Snapshot一致。响应不包含领域对象、ORM、Session、历史Revision、ETag字段或安全令牌。

## 强ETag和并发

Story Bible与Project复用公共的强版本协议：

```text
ETag: "N"
If-Match: "N"
```

`N`只能是无前导零的正signed-64位整数。弱ETag、`*`、多值、未加引号、空白、零、负数、小数、指数和溢出均拒绝。PUT缺少If-Match返回428 `PRECONDITION_REQUIRED`，格式非法返回400 `INVALID_IF_MATCH`，stale返回412 `STORY_BIBLE_VERSION_CONFLICT`，其details只包含安全的`expected_version`与`actual_version`。服务不预先GET、不自动获取新版本、不重试、不合并；成功响应Header中的ETag严格等于JSON的`concurrency_version`。

## 安全、错误和缓存

POST与PUT继承本地写请求的Host、可信Origin、进程内Session、CSRF、JSON媒体类型和固定1 MiB正文上限。GET不要求Session、CSRF或Origin，但仍经过Host、请求ID和安全响应头。所有成功响应设置`Cache-Control: no-store`；POST另返回指向稳定资源的相对`Location`。统一错误结构始终包含request ID，不回显If-Match、title、content、SQL、数据库路径、Cookie、CSRF或堆栈。

稳定映射包括：

| 条件 | HTTP | code |
| --- | ---: | --- |
| 非法Project/Story Bible ID | 422 | `INVALID_PROJECT_ID` / `INVALID_STORY_BIBLE_ID` |
| 非法title/content或DTO | 422 | `INVALID_STORY_BIBLE_TITLE` / `INVALID_STORY_BIBLE_CONTENT` / `REQUEST_VALIDATION_ERROR` |
| Project不存在 | 404 | `PROJECT_NOT_FOUND` |
| Project存在但无Story Bible | 404 | `STORY_BIBLE_FOR_PROJECT_NOT_FOUND` |
| Story Bible不存在 | 404 | `STORY_BIBLE_NOT_FOUND` |
| 同Project重复创建/ID冲突 | 409 | `STORY_BIBLE_ALREADY_EXISTS_FOR_PROJECT` / `STORY_BIBLE_ID_CONFLICT` |
| stale | 412 | `STORY_BIBLE_VERSION_CONFLICT` |
| 数据损坏 | 500 | `STORY_BIBLE_DATA_CORRUPTION` |
| 持久化或服务不可用 | 503 | `STORY_BIBLE_PERSISTENCE_UNAVAILABLE` / `STORY_BIBLE_SERVICE_UNAVAILABLE` |

空数据库或仅迁移至0002的数据库不会被应用自动迁移。合法Story Bible请求安全返回503 `STORY_BIBLE_PERSISTENCE_UNAVAILABLE`，live仍可返回200，且不会创建三张Story Bible表。

## 组合根与OpenAPI

FastAPI lifespan复用唯一Engine和Session factory，显式装配`SqlAlchemyStoryBibleRepository`、`StoryBibleCommandService`与`StoryBibleQueryService`，并注入公共UTC Clock以及`StoryBibleId.new`、`StoryBibleRevisionId.new`。Router只读取`app.state`中的应用服务，不创建Repository、Session、Clock或ID；lifespan关闭时清除引用。应用工厂构造本身不连接数据库或迁移Schema。

development/test OpenAPI登记四条Story Bible操作、`Story Bible`标签、严格Schema、完整替换、ETag/If-Match和适用错误响应。production的`/docs`、`/redoc`和`/openapi.json`继续关闭且不进入SPA。

## 验证证据与后续边界

专项测试覆盖DTO、显式Mapper、错误、Router、安全、共享ETag、真实0003流程、双服务并发、未迁移数据库、OpenAPI和AST架构边界。`E2E-INT-011`通过真实production集成进程验证Project创建、Story Bible创建、两种GET、完整PUT、stale 412和安全写边界；`E2E-INT-012`从真实前端调用同一协议，验证POST一次、GET刷新、PUT完整替换和显式冲突恢复。

当前Revision表继续由0003不可变触发器保护，但没有Revision列表或单Revision读取API。前端状态与安全契约见[Story Bible前端流程](STORY_BIBLE_FRONTEND.md)；该页面不把历史、结构化实体或AI能力声明为已完成。
