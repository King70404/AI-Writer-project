# Story Bible不可变修订历史

DEV-2.6在既有Story Bible领域、0003三表、事务Repository、应用用例、HTTP和纯文本前端之上增加只读历史能力。范围仅包括按Story Bible列出不可变修订摘要、按RevisionNumber读取一份完整历史快照，以及Project归属的前端查看页；没有Diff、回滚、恢复、采用、历史编辑或删除。

## 端口与读取事务

`StoryBibleRevisionHistoryReader`是专用只读端口，提供`list_revisions()`与`get_revision()`。它与负责当前Aggregate写入和读取的`StoryBibleRepository`分离：历史查询不需要构造当前Aggregate，不应继承`BEGIN IMMEDIATE`、CAS、Clock、ID Factory或写事务语义，也不能扩大写Repository契约。

`SqlAlchemyStoryBibleRevisionHistoryReader`每次调用创建一个独立Session，使用普通只读事务，最多执行两个业务SELECT：第一个同时验证稳定对象、Project归属、Head及Head所指Revision；第二个读取一页摘要或一条完整Revision。它不写表、不提交、不重试、不自动迁移，并在成功或失败后rollback并关闭Session。

## Head权威

`story_bible_heads.revision_id`是当前Revision的唯一权威。读取器显式连接Head及其归属Revision，并验证Stable concurrency version、Head和当前RevisionNumber一致；不能用`MAX(revision_number)`、最后创建时间或列表第一项推断当前状态。缺失Head、跨Story Bible Head、断裂引用、版本或时间不一致均是`StoryBibleDataCorruption`，不会被修复或伪装为404。

## 应用读取模型

历史摘要只包含：

- `revision_id`
- `revision_number`
- `title`
- `created_at`
- `is_current`

单Revision快照包含`story_bible_id`、`project_id`、上述Revision身份、编号、标题和创建时间，并增加完整`content`、`is_current`与`current_revision_number`。模型不可变、仅保存传输原语、严格验证规范ID、正的64位RevisionNumber、Story Bible文本规则及aware UTC时间；不暴露ORM、Session、Repository、ETag或HTTP对象。

## 排序、Keyset与游标

列表固定按`RevisionNumber DESC`排序。`limit`默认20、最小1、最大100；SQL读取`limit + 1`判断`has_more`，不执行COUNT、OFFSET或页码查询。后续页固定使用：

```text
story_bible_id = 请求中的Story Bible
revision_number < after_revision_number
ORDER BY revision_number DESC
LIMIT limit + 1
```

游标载荷固定为版本1、`story_bible_id`和`after_revision_number`。编码使用UTF-8、键排序、紧凑JSON、Base64url且去除padding，最长256个ASCII字符。解码拒绝重复键、额外键、未知版本、非规范JSON/Base64url、bool或溢出RevisionNumber、非规范ID及跨Story Bible复用。游标是不可信且不透明的分页位置，不是凭据，也不提供跨请求一致性快照；新增Revision后旧游标仍只继续读取严格更小的编号。

列表SELECT只读取Revision ID、RevisionNumber、title和created_at，不读取content。单Revision正文仅在用户明确选择后通过独立GET读取。

## 错误语义

Story Bible不存在时传播`StoryBibleNotFound`并映射`STORY_BIBLE_NOT_FOUND`；Story Bible存在但指定RevisionNumber不存在时使用`StoryBibleRevisionNotFound`并映射`STORY_BIBLE_REVISION_NOT_FOUND`。持久化损坏和数据库不可用分别保持安全的500与503语义，不能转成空列表或404。错误、日志和游标失败不会包含title、content、SQL、路径、游标原文或对象`repr`。

## HTTP接口

只新增两条GET：

```text
GET /api/v1/story-bibles/{story_bible_id}/revisions
GET /api/v1/story-bibles/{story_bible_id}/revisions/{revision_number}
```

列表支持`limit`与不透明`cursor`；单Revision要求规范正十进制编号。两个响应都发送`Cache-Control: no-store`，不发送ETag，不创建或要求本地Session，不要求CSRF，也不接受写入语义。production API总数为15。

## 前端历史页

前端路由固定为：

```text
/projects/:projectId/story-bible/history
```

URL只保存Project ID。进入页面后先按Project读取当前Story Bible以取得Story Bible ID，再请求第一页历史摘要；首屏不自动请求任一单Revision正文。列表展示修订号、标题、创建时间和当前标记。“加载更多”原样传递服务端游标并追加去重结果，不把游标写入URL或浏览器存储。点击一项才请求正文；新选择会Abort旧请求，并以generation检查忽略迟到响应。

标题、正文、Revision ID、ETag、游标和草稿都不写入`localStorage`、`sessionStorage`、Cookie、URL或日志。历史GET不获取Security Session。页面只提供查看和返回编辑页，不提供Diff、回滚、恢复、采用、历史编辑或删除。

## 当前限制与下一步

DEV-2.6没有修改Schema、迁移、不可变触发器、当前写Repository、Project数据或Story Bible完整替换语义，也没有新增依赖。没有Character、World、PowerSystem、Planning、三区、审批、Codex、Agent、Skill或Prompt。

DEV-2.7只能在独立编号任务明确授权后继续；本历史基础不预先授权结构化设定实体、历史写操作、Diff、回滚、恢复、搜索或AI生成。
