# Project 不可变修订历史

DEV-1.9 在既有 Project 三表和不可变 Revision 之上增加纯读取能力：历史摘要列表、按编号读取单个 Revision，以及 `/projects/:projectId/history` React 页面。该能力不改变 Schema，不提供历史写入、回滚、恢复、Diff、删除或审计作者。

## 数据来源与不可变性

历史数据来自显式迁移到 `0002_create_project_foundation` 的 `project_revisions`；数据库中的 `trg_project_revisions_no_update` 和 `trg_project_revisions_no_delete` 触发器分别拒绝 UPDATE 与 DELETE。Reader 只执行 SELECT，当前 Revision 标记来自 `project_heads.revision_id` 所指向 Revision 的 `revision_number`，不能用最大 RevisionNumber 猜测当前值。Head 是当前状态的权威所有者，Revision 是不可变历史正文的权威所有者。

历史列表 Item 精确包含：

- `revision_id`；
- `revision_number`；
- `title`；
- `created_at`；
- `is_current`。

列表不返回 `description`，避免初始页面和分页请求批量加载正文、扩大内存与传输范围。单 Revision 响应才返回 `project_id`、`revision_id`、`revision_number`、`title`、`description`、`created_at`、`is_current` 和 `current_revision_number`；它仍是只读快照。

## 排序与 Keyset 分页

历史固定按 `revision_number DESC` 排序。默认 `limit=20`，合法范围为 1 至 100。下一页条件只有同一 Project 内的 `revision_number < cursor.revision_number`；查询使用 `limit + 1` 判断 `has_more`，不执行 COUNT、OFFSET，也不返回 total。

版本 1 cursor 是规范 UTF-8 JSON 的无填充 Base64url 编码，载荷只包含版本、Project ID 和最后返回的 RevisionNumber。解码严格拒绝重复键、额外字段、非规范编码、非法编号和 Project 不匹配。cursor 绑定 Project，但它不是授权凭据、安全令牌或数据库快照，也不应进入日志或浏览器存储。

多次 HTTP 请求之间没有数据库快照隔离。取得旧 cursor 后产生的新 Revision 会出现在新的第一页前部，不会进入该旧 cursor 的后续页；已取得的旧 Revision 内容仍因数据库不可变约束而保持不变。页面不会声称实时同步或跨请求完全冻结。

## Reader 的损坏策略

每次读取先用 Project、Head 和当前 Revision 的权威关系确认 Project 当前状态，再读取目标历史范围。已读取行中的 ID、所有权、编号、标题、简介或时间不合法时，整个调用以安全的 `ProjectDataCorruption` 失败；不返回部分数据、不静默跳过，也不回显正文、cursor、SQL、数据库路径或底层异常。

Reader 只验证当前状态及本次查询实际读取的行，不扫描未读取的全部历史，因此不是离线全库审计工具。每个调用使用独立 Session，完成或失败都 rollback 并 close；它不调用写 Repository，也不执行业务写 SQL。

## HTTP 与前端

只读接口为：

```text
GET /api/v1/projects/{project_id}/revisions
GET /api/v1/projects/{project_id}/revisions/{revision_number}
```

两个 GET 都不要求 Security Session、CSRF 或 Origin，不接收正文，不返回 ETag，并设置 `Cache-Control: no-store`；Host、安全响应头和统一错误隐私仍有效。列表的 cursor 只由后端编码和解析，前端把它当作不透明字符串经 `URLSearchParams` 原样带回。

历史页面先读取摘要，明确标记当前 Revision；只有用户点击真实按钮时才按需读取一个 Revision 正文。这样不会自动加载全部正文。加载更多只追加一页，失败时保留已有条目和 cursor；切换选中项会取消旧请求并忽略迟到响应。正文按纯文本显示并保留换行，不写入 URL、Cookie、`localStorage`、`sessionStorage`、日志或诊断文件。

当前没有回滚、恢复、Diff、历史编辑、历史删除、自动连续加载或无限滚动。DEV-1.10 的 M1 验收只能在独立任务中核对阶段 1 已实现能力、冻结边界、回归证据和未实现项；本文件不提前执行或声明该验收。
