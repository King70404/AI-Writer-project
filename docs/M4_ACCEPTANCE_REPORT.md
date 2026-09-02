# M4 Novel Structure Foundation 验收报告

## 验收结论

M4 在 M0 工程底座、M1 Project、M2 Story Bible 与 M3 Character 冻结基线之上，完成并正式验收 Outline、Volume、Chapter 组成的小说结构管理基础。本次冻结只记录已经由真实后端、前端与端到端测试证明的能力，不扩展到章节正文或 M5 写作工作台。

M4 Novel Structure基础能力验收通过。

## 实现基线与提交链

- implementation HEAD：`5efb18251c5d93de8cd53b907d16bdf96e021e32`
- implementation tree：`1086cd604dfd77344ba1c42465bd4a42b791582f`
- implementation commit count：46
- implementation tracked files：654
- branch：`main`
- Git remote：无

M4 的 5 个实现提交依次为：

1. `2a7f3e110c842478ccb5b3153ce35656e61c0816` — `feat(novel-structure): establish outline volume chapter model`
2. `96aa7a4425901566832a3eace508294128dd49e5` — `feat(novel-structure): add transactional persistence`
3. `4034ffc5d2bfa51158358b7661bed56d224a1a1d` — `feat(novel-structure): add application use cases`
4. `47fdf12a91b58a0c7ca6ea5cfa8b4b2001639d93` — `feat(novel-structure): expose HTTP API`
5. `5efb18251c5d93de8cd53b907d16bdf96e021e32` — `feat(frontend): add novel structure workspace`

## 冻结能力

### Outline

每个 Project 最多拥有一个 Outline。Outline 采用 stable object、immutable revisions、head authority 与 optimistic concurrency，保存 `title` 和 `summary`。已实现创建、按 Project 读取、更新，以及前端创建、读取和编辑；单资源响应使用强 ETag，更新要求 If-Match。

### Volume

每个 Project 可拥有 0..N 个 Volume。Volume 保存 `title`、`summary` 和 `position`；当前 `position` 在 Project 内唯一，列表按 `position ASC` 返回。历史 Revision 的旧 position 可以与其他 Volume 的当前 position 重复。已实现创建、读取、列表、更新，以及前端创建、列表、选择和编辑。

### Chapter

每个 Volume 可拥有 0..N 个 Chapter。Chapter 同时绑定 `project_id` 与 `volume_id`，且两者的 Project 归属必须一致。Chapter 保存 `title`、`summary` 和 `position`；当前 `position` 在 Volume 内唯一，列表按 `position ASC` 返回。已实现创建、读取、列表、更新，以及前端创建、列表和编辑。

Chapter 当前只表示小说结构节点。M4 没有 Chapter 正文 `content` 或 `body`，也没有正文编辑器、Markdown、word count、draft、writing status 或 Autosave。

## 领域与应用架构

Outline、Volume、Chapter 延续 stable object + immutable revisions + head 模式。对象与 Revision ID 前缀分别为 `out_`、`orv_`、`vol_`、`vrv_`、`chp_`、`chv_`。Revision number 从 1 开始，是严格递增的正整数。

`title` 会 trim、不得为空且最长 120 字符；`summary` 可为空、最长 2000 字符并规范化换行。Volume 和 Chapter 的 `position` 范围为 1..2^63-1。

应用层冻结的用例为：

- Outline：Create、Get、GetByProject、Update；
- Volume：Create、Get、List、Update；
- Chapter：Create、Get、List、Update。

用例继续验证 Project 存在性、Chapter/Volume 归属、当前位置冲突、Outline 唯一性与乐观并发。当前没有 delete、archive、restore、reorder、move 或 history queries。

## 持久化与迁移

正式 Metadata 精确为 18 张业务表。M4 新增：`outlines`、`outline_revisions`、`outline_heads`、`volumes`、`volume_revisions`、`volume_heads`、`chapters`、`chapter_revisions`、`chapter_heads`。

Alembic head 为 `0005_create_novel_structure_foundation`，不存在 0006。迁移 Git blob 为：

- 0001：`63112b9b7d4510decb9b38de07ceb867491f2e05`
- 0002：`5aa10200b7290278000cc21951850960dc914089`
- 0003：`deb9c9c05fa2af8dd78c701c1afe72fb26b7fc99`
- 0004：`175044bfad61a4595000e4ec3dc01c5db6b3e641`
- 0005：`2982c22e8406d74b9a913f2b468137484c7490dc`

独立迁移数据库的 Revision 不可变触发器精确为 12 个：Project、Story Bible、Character、Outline、Volume、Chapter 各有 no-update 与 no-delete。SQLite 继续启用 WAL 与 foreign keys。

## HTTP API 与并发协议

真实 production OpenAPI 精确为 32 个 operation，其中 Novel Structure 为 11 个，旧 Project-owned 模块 operation 为 6 个。Novel Structure 包含 Outline 3 个、Volume 4 个、Chapter 4 个 operation；完整 method/path 库存在 Baseline Manifest 中。

单资源响应使用强 ETag；PUT 必须携带 If-Match。缺失 If-Match 返回 428，格式错误返回 400，陈旧版本返回 412。Outline 已存在、Volume position 冲突、Chapter position 冲突及 Chapter/Volume 归属不一致返回 409；资源不存在返回 404。客户端不会自动重试或覆盖最新服务器状态。

## 前端 Novel Structure Workspace

前端 production routes 精确为 11 条，M4 只新增 `/projects/:projectId/structure`。Project 详情页提供“小说结构”入口；一个统一 Workspace 管理 Outline、Volumes 和 Chapters，而不是三个独立页面。

- Outline：空状态、创建、编辑；
- Volume：列表、创建、选择、编辑和 position 排序；
- Chapter：当前 Volume 的章节列表、创建、编辑和 position 排序。

创建 Volume 的默认 position 为当前最大 position + 1；创建 Chapter 的默认 position 为当前 Volume 最大 position + 1，用户仍可修改，后端仍要求显式 position。当前没有 drag-and-drop、automatic swapping 或 bulk reorder。

前端保存真实 ETag 并在更新时发送 If-Match。409 显示明确业务冲突，412 显示陈旧版本冲突；两者均不自动重试，也不覆盖服务器最新状态。

## 正式质量证据

三份 M4 文档创建前，在 implementation HEAD 上严格按精简冻结策略执行一次 Default 和一次 IncludeE2E；两次均以真实退出码 0 完成，没有失败重跑，也没有在文档后重复执行完整门禁。

- Backend：2559/2559 通过；statements `9742/10005`（97.37%），branches `2023/2162`（93.57%）。
- Frontend：46 个测试文件、510 项测试通过；statements `2728/2840`（96.05%），branches `2551/2788`（91.49%），functions `659/664`（99.24%），lines `2650/2741`（96.68%）。
- E2E：development 3、integration 17、missing-build-state 1，共 21/21 通过。
- `E2E-INT-017` 验证真实 Project、structure route、Outline、两个 Volume 与两个 Chapter 的创建和 position 排序，以及 Outline、Volume、Chapter 更新、真实 ETag 和浏览器审计。
- 关键旧回归 `E2E-DEV-001`、`E2E-INT-008`、`E2E-INT-010`、`E2E-INT-014`、`E2E-INT-015`、`E2E-INT-016` 均通过。

M4 没有新增 npm 依赖，`frontend/package.json` 与 `frontend/package-lock.json` 相对 M3 tag 无差异；本次 M4 精简冻结未重复执行 DependencyAudit。

## M0-M3 冻结保护

M0、M1、M2、M3 的 annotated tag 对象、目标与消息均保持不变。12 份旧 Acceptance 冻结文件相对各自 tag 无差异，本任务没有改写旧历史或旧冻结事实。

## 安全与架构

系统继续保持 local-first、single-user、仅绑定 `127.0.0.1`、SQLite WAL/FK、模块化单体和无 Git remote。运行栈为 Python 3.12.10、FastAPI、SQLAlchemy 2、Alembic，以及 React、TypeScript、Vite、React Router 8.3.0。没有云凭据、遥测、推送或云集成。

## 明确范围边界

以下均未实现，且不属于 M4 缺陷：Chapter 正文、正文编辑器、Markdown/rich text、word count、draft、writing status、Autosave、浏览器草稿恢复；AI generation/rewrite/continuation/context assembly；Agent、Skills、Prompt management；Outline/Volume/Chapter 历史 UI、rollback、restore、diff、delete、archive；drag-and-drop、bulk reorder、Chapter 跨 Volume 移动；World、Location、Organization、Character relationships；publishing、release workflow、cloud integration、remote Git。M5 未在本次任务中开始。
