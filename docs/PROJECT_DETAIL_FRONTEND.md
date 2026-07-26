# Project 详情与修订前端流程

DEV-1.8 在不改变数据库 Schema 或 `0002_create_project_foundation` 的前提下，为既有 Project 当前快照 API 提供 React 详情、完整修订与显式并发冲突处理。DEV-1.9仅在详情页增加通往独立只读历史页的链接；本页仍只编辑当前版本，不编辑任何历史Revision。

## 路由、读取与版本资源

1. `/projects/:projectId` 只接受规范 Project ID。路由参数在网络调用前验证，构造 API 路径时使用 `encodeURIComponent`；非法值不请求服务端，也不回显原值。
2. 详情客户端调用一次同源 `GET /api/v1/projects/{project_id}`。该安全读取不获取 Security Session，不发送 CSRF、`If-Match` 或请求正文。
3. `VersionedProjectResource` 把严格解析的 `ProjectResponse` 与同一响应的强 ETag 绑定，作为编辑所需的不可分割版本资源。
4. ETag 只接受精确的 `"<positive-safe-integer>"`：拒绝弱标签、列表、空白、零、前导零、负数和超出 JavaScript 安全整数范围的值。
5. ETag 数值必须与正文 `concurrency_version` 完全一致；不一致、缺失或非法响应均按契约错误处理，不能进入编辑状态。
6. 编辑基线是最后一次已确认的 `VersionedProjectResource`，表单草稿只存在于当前 React 内存状态。列表摘要不能代替详情 GET 的基线。

## 完整修订与结果语义

7. 保存使用一次 `PUT /api/v1/projects/{project_id}`，正文只含完整的 `title` 与 `description`；它是完整替换，不是 PATCH。
8. `If-Match` 必须直接来自当前编辑基线的已验证强 ETag，不能由正文版本重新拼接，也不能从浏览器存储读取。
9. 保存顺序固定为：先完成本地 ID、ETag 与字段验证，再按需取得内存 Security Session，随后发送带 `Content-Type`、`X-CSRF-Token`、`If-Match` 的唯一 PUT。
10. PUT 前不预先 GET。服务端 Repository 在写事务内执行 CAS；预读既不能消除竞态，还会扩大请求和状态窗口。
11. PUT 不自动重试或重放。响应丢失时，首次写入可能已经成功，自动重试会创建意外的下一条 Revision。
12. PUT 开始后的网络中断或 abort 属于“保存结果未知”：保留草稿、禁用再次保存，并要求用户显式重新加载项目核实服务端状态。

## 412 冲突与显式恢复

13. 只有结构、错误码和 `expected_version`/`actual_version` 均严格合法的 412 才进入冲突状态；畸形 412 是契约错误。
14. 冲突发生时保留提交时锁定的完整本地草稿与原始基线，不把服务端错误正文当作可信 UI 内容。
15. 冲突后不会自动 GET。用户必须点击“读取最新版本”，客户端才执行一次显式详情 GET；失败时仍保留草稿并允许手动重试读取。
16. “放弃当前草稿并采用最新版本”会把已读取的最新资源设为基线和表单值，不发送 PUT。
17. “保留草稿并以最新版本建立基线”只替换基线 ETag，保持标题和简介草稿原样，不立即发送 PUT。
18. 上述行为不是自动合并：客户端不比较、拼接或逐字段裁决两份正文，用户看到两份预览后作出整体选择。
19. 保留草稿并重建基线后，用户必须再次点击保存；第二次手动 PUT 才使用最新 ETag 提交完整草稿。

## 安全边界与当前限制

20. ETag、草稿、CSRF 与冲突状态都不得写入 `localStorage`、`sessionStorage`、IndexedDB、Cookie、URL、日志或诊断文件；刷新意味着重新 GET。
21. 详情页提供真实“查看修订历史”链接，进入`/projects/:projectId/history`；历史页面与本页编辑状态分离，详情表单不会加载或修改历史正文。
22. 当前没有历史回滚、恢复、Diff、编辑或删除，也没有Project删除、归档或自动保存；详情页不提供 Character、Chapter、三区、审批或 Codex 功能。
23. 历史读取的Keyset、按需正文和安全边界见[Project不可变修订历史](PROJECT_REVISION_HISTORY.md)；它不改变本文件的PUT并发与显式冲突语义。

## 验证证据

七个详情专项 Vitest 文件覆盖强 ETag、详情协议、修订协议、页面状态、表单、冲突恢复和路由，共 79 项测试；新增详情生产代码专项覆盖率为 statements 97.43%、branches 91.38%、functions 100%、lines 97.40%。`E2E-INT-009`在显式迁移的临时 SQLite 上验证真实 UI 创建与详情读取、一次正常 v1→v2 修订，以及另一 Project 的 v1 基线、外部 v2、412、显式读取、保留草稿和手动 v3 保存，并校验不可变 Revision 链与清理。
