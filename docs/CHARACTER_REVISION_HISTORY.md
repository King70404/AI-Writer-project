# Character不可变Revision历史

DEV-3.6在既有Character三表和写Repository之外增加只读历史能力。它只读取已经存在的不可变Revision，不提供恢复、回滚、Diff、历史编辑、删除或任何历史写操作。

## 接口与前端路由

- `GET /api/v1/characters/{character_id}/revisions`返回历史摘要页；支持`limit`和不透明`cursor`。
- `GET /api/v1/characters/{character_id}/revisions/{revision_number}`返回一个完整Revision。
- `/projects/:projectId/characters/:characterId/history`提供React只读历史页，并由当前Character编辑页的“查看修订历史”链接进入。

两个GET都无需Security Session或CSRF，不接受ETag、`If-Match`或请求正文，响应使用`Cache-Control: no-store`。production API精确为21条，前端路由精确为10条。

## Reader边界

纯应用端口`CharacterRevisionHistoryReader`与写`CharacterRepository`分离；`CharacterRevisionHistoryQueryService`每个用例只调用Reader一次。SQLAlchemy适配器使用每次调用独立的普通Session，不提交事务，也不导入Web层。

列表摘要字段为`revision_id`、`revision_number`、`name`、`role`、`created_at`和`is_current`，不读取或返回`profile`。单Revision详情另返回完整`profile`和`current_revision_number`。所有应用模型均不可变、只含脱离Session的原语与aware UTC时间。

## Head权威与查询规则

`character_heads.revision_id`是current的唯一权威；最大RevisionNumber不能替代Head。列表固定按`RevisionNumber DESC`排序，游标之后使用严格`revision_number < after_revision_number`的keyset条件。Reader取`limit + 1`行判断`has_more`，返回至多`limit`项，不执行`COUNT`或`OFFSET`。

每次列表最多两个业务SELECT：先读取Character与Head权威状态，再读取摘要页。详情同样最多两个SELECT：先读取Character与Head，再按精确RevisionNumber读取完整Revision。列表SQL不选择`profile`列。

## Cursor

cursor是UTF-8 JSON的无填充base64url编码，载荷字段精确为：

```json
{"after_revision_number":20,"character_id":"chr_...","v":1}
```

载荷长度上限256字符，严格拒绝未知字段、非规范编码、非正整数、bool、溢出、非规范Character ID和跨Character复用。cursor只表示历史位置，不是安全凭据，也不是数据库快照；创建新Revision后，旧cursor仍按其既有严格下界继续读取。

## 错误与未迁移状态

Character不存在返回`CHARACTER_NOT_FOUND` 404；Character存在但指定Revision不存在返回`CHARACTER_REVISION_NOT_FOUND` 404。非法Character ID或RevisionNumber返回422，非法cursor返回400；数据损坏返回安全500，Reader或Schema不可用返回安全503。空数据库和只迁移到0003的数据库不会自动迁移，历史接口安全返回503。错误不回显name、role、profile、cursor、SQL、数据库路径或异常对象。

## 前端读取流程

历史页首屏只发一个列表GET，不发详情GET。用户点击“加载更多”时沿当前cursor追加严格降序且无重复的摘要；失败保留已加载数据和cursor，非法cursor允许显式重载第一页。用户点击“查看此修订”后才发一个详情GET，不从摘要拼装profile。

路由变化、卸载、重载与快速切换都会取消旧请求，并使用请求代际阻止迟到响应覆盖当前选择。Abort不显示为普通错误。profile以纯文本`pre`呈现并保留换行，不使用Markdown或`dangerouslySetInnerHTML`。

## 隐私与无障碍

cursor、profile和历史响应不进入URL查询、history state、localStorage、sessionStorage、IndexedDB、Cookie、日志、隐藏DOM或data属性。页面使用唯一主标题、语义列表、原生Link/button、loading `role=status`、error `role=alert`、`aria-pressed`、`time`元素，并在详情成功后聚焦详情标题。

## 验证与后续范围

专项测试覆盖严格模型、Reader/Service单次调用、Head权威、最多两个SELECT、21+分页、23 Revision无重复遗漏、新Revision与旧cursor、损坏、未迁移503、DTO/OpenAPI、安全和前端取消竞态。`E2E-INT-016`在真实生产构建与临时0004 SQLite上验证入口、直接刷新、20+1分页、按需profile、快速选择、无写入、数据库不可变性和清理。

DEV-3.7如获单独授权，可继续阶段3后续明确任务；本文件不预先授权Character关系、World、PowerSystem、恢复、回滚、Diff、历史编辑、删除、规划、章节、Codex、Agent或AI生成。
