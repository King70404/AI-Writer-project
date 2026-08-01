# Character HTTP API

## 范围与资源路径

DEV-3.4只开放四个本地后端接口：

```text
GET  /api/v1/projects/{project_id}/characters
POST /api/v1/projects/{project_id}/characters
GET  /api/v1/characters/{character_id}
PUT  /api/v1/characters/{character_id}
```

创建和列表使用Project嵌套路径，因为两者都以归属Project为明确边界；当前读取和修订使用稳定Character资源路径，因为Character身份由`CharacterId`唯一决定。一个Project可以拥有多个Character，同名Character合法。

DEV-3.5现已在这四条操作上建立Character稳定列表/创建/当前完整修订前端，见[Character前端流程](CHARACTER_FRONTEND.md)。当前仍没有Revision历史、关系接口、PATCH、删除、归档、恢复或AI生成。

## DTO与显式映射

`CreateCharacterRequest`包含必需`name`，以及默认空字符串的`role`、`profile`。`ReviseCharacterRequest`要求`name`、`role`、`profile`全部存在，表示完整替换；`null`、额外字段和自动类型强转均被拒绝。

`CharacterResponse`包含：

```text
character_id
project_id
current_revision_id
revision_number
concurrency_version
name
role
profile
created_at
updated_at
revision_created_at
head_updated_at
```

列表项只包含`character_id`、`current_revision_id`、两个版本、`name`、`role`、`created_at`和`updated_at`，故意不读取或返回`profile`。列表页包含`project_id`、不可变`items`、`next_cursor`和`has_more`，不返回`total`。Web Mapper逐字段复制请求和应用Snapshot/Page，不使用ORM、反射或Pydantic快捷序列化代替边界映射。

## 稳定列表与严格游标

固定排序为：

```text
created_at DESC, character_id DESC
```

`limit`默认20，范围1至100。持久化Reader使用复合Keyset和`limit + 1`，不使用OFFSET或COUNT。游标是UTF-8紧凑JSON经无填充Base64url编码，键精确为：

```json
{
  "v": 1,
  "project_id": "prj_...",
  "after_created_at": "2026-07-29T08:09:10.123456Z",
  "after_character_id": "chr_..."
}
```

JSON键排序、无多余空白，时间固定六位微秒UTC `Z`，最大512字符。解析拒绝填充、重复/缺失/额外键、非规范ID或时间、未知版本和跨Project复用。游标只是Project绑定的读取位置，不是权限凭据，也不是跨请求数据库快照；页间新增的靠前Character不会改变旧游标之后的位置语义。

## ETag、完整替换与并发

POST成功返回201、相对`Location`、`Cache-Control: no-store`和代表`ConcurrencyVersion`的共享强ETag（例如`"1"`）。按ID GET和PUT成功也返回强ETag与`no-store`；列表GET只返回`no-store`，没有资源ETag。

PUT必须提供一个规范强`If-Match: "N"`。缺失返回428，弱ETag、通配符、重复或其他非法格式返回400，stale返回412并保留安全的`expected_version`和`actual_version`。Router不预先GET、不重试、不合并；Clock和Revision ID Factory仍由Repository在事务内按stale优先级调用。成功PUT完整替换三个正文值，空`role`或`profile`是明确新值。

## 本地安全与错误

POST和PUT继承现有Host、请求体上限、严格JSON、允许Origin、本地安全Session与CSRF要求。两个GET不创建或要求Session、CSRF或Origin。所有响应继续带request ID和安全响应头；正文、CSRF、Session、If-Match、游标、SQL和本机路径不得进入日志或错误。

稳定映射包括：非法字段/ID为422，Project或Character不存在为404，ID冲突为409，stale为412，数据损坏为500，持久化或未迁移数据库为503。请求体过大为413，非UTF-8 JSON媒体类型为415。错误不会把数据库失败伪装为不存在。

## 组合根、OpenAPI与迁移

`main`在唯一Engine和Session factory之上装配`SqlAlchemyCharacterRepository`、`SqlAlchemyCharacterListReader`、`CharacterCommandService`和`CharacterQueryService`；Router只依赖应用服务契约，不访问Session、ORM或SQL。导入Web包不连接数据库、不迁移、不生成ID。

生产OpenAPI精确登记四个新操作，总API操作数为19；生产文档入口仍关闭并与SPA回退隔离。Alembic head仍是`0004_create_character_foundation`，Metadata仍为九表，没有0005。空数据库或只迁移到0003的数据库不会自动迁移，四个合法Character操作安全返回503。
