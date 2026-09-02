# M4 Novel Structure Foundation 验收清单

本清单中的“通过”只表示证据符合 M4 冻结范围；“未实现（符合范围）”是明确的 scope boundary，不是已完成能力。

## 已实现并通过

| Check | Evidence | Result |
| --- | --- | --- |
| 实现基线 | HEAD `5efb18251c5d93de8cd53b907d16bdf96e021e32`，tree `1086cd604dfd77344ba1c42465bd4a42b791582f`，46 commits，654 tracked files | 通过 |
| Git 起始状态 | `main`；worktree、staging、remote 均为空；三份 M4 文件与 M4 tag 不存在 | 通过 |
| M0-M3 冻结 | 四个 annotated tag 身份不变；12 份旧冻结文件相对各自 tag 无差异 | 通过 |
| M4 实现链 | 5 个规定提交的顺序、完整哈希与主题一致 | 通过 |
| Outline | 单 Project 唯一、stable object、immutable revisions、head、创建/按 Project 读取/更新及前端创建编辑 | 通过 |
| Volume | Project 内多对象、当前位置唯一、position ASC、创建/读取/列表/更新及前端选择编辑 | 通过 |
| Chapter | Volume 内多对象、Project 归属一致、当前位置唯一、position ASC、创建/读取/列表/更新及前端编辑 | 通过 |
| 领域约束 | 六类 ID 前缀；Revision 从 1 严格递增；title/summary/position 规则完整 | 通过 |
| 应用用例 | Outline 4、Volume 4、Chapter 4 类最小命令/查询能力及业务验证 | 通过 |
| HTTP 并发 | 强 ETag、If-Match；缺失 428、格式错误 400、stale 412；业务冲突 409 | 通过 |
| Production API | 实际 OpenAPI 精确 32 operations，其中 Novel Structure 11、Project-owned 6 | 通过 |
| Frontend routes | 11 个带 path 路由；M4 只新增 `/projects/:projectId/structure` | 通过 |
| Workspace | Project 详情入口；统一管理 Outline、Volumes、Chapters；空态、创建、选择、编辑和排序 | 通过 |
| 默认 position | Volume 为 Project 当前最大值 + 1；Chapter 为当前 Volume 最大值 + 1；用户仍可编辑 | 通过 |
| Metadata | 18 张业务表，其中 M4 新增 9 张 Novel Structure 表 | 通过 |
| Alembic | head `0005_create_novel_structure_foundation`；不存在 0006 | 通过 |
| Migration blobs | 0001 至 0005 的 Git blob 与冻结值逐项一致 | 通过 |
| Revision triggers | 实际迁移 schema 中 12 个 no-update/no-delete 触发器 | 通过 |
| Default 正式门 | 文档创建前仅运行一次，真实退出码 0 | 通过 |
| Backend | 2559/2559；statements 9742/10005（97.37%），branches 2023/2162（93.57%） | 通过 |
| Frontend | 46 files/510 tests；statements 96.05%、branches 91.49%、functions 99.24%、lines 96.68% | 通过 |
| IncludeE2E 正式门 | 文档创建前仅运行一次，真实退出码 0，清理检查通过 | 通过 |
| E2E 库存 | development 3、integration 17、missing-build-state 1，共 21/21 | 通过 |
| M4 E2E | `E2E-INT-017` 覆盖统一 Workspace、排序、更新、真实 ETag 与浏览器审计 | 通过 |
| 关键旧 E2E | DEV-001、INT-008、010、014、015、016 均通过 | 通过 |
| npm 依赖 | M4 相对 M3 未修改 package manifests；按精简冻结策略未执行 DependencyAudit | 通过 |
| 安全与架构 | local-first、single-user、127.0.0.1、SQLite WAL/FK、模块化单体；无云凭据、遥测或 remote | 通过 |
| 文档范围 | 只新增三份 M4 验收文件；不修改产品、测试、配置、依赖或旧冻结文件 | 通过 |

## Scope boundary / not implemented

| Capability | Result |
| --- | --- |
| Chapter 正文、content/body、正文编辑器、Markdown/rich text、word count、draft、writing status | 未实现（符合范围） |
| Autosave、浏览器草稿恢复 | 未实现（符合范围） |
| AI generation/rewrite/continuation/context assembly | 未实现（符合范围） |
| Agent、Skills、Prompt management | 未实现（符合范围） |
| Outline/Volume/Chapter 历史 UI、rollback、restore、diff | 未实现（符合范围） |
| delete、archive | 未实现（符合范围） |
| drag-and-drop、automatic swapping、bulk reorder、Chapter 跨 Volume 移动 | 未实现（符合范围） |
| World、Location、Organization、Character relationships | 未实现（符合范围） |
| publishing、release workflow、cloud integration、remote Git | 未实现（符合范围） |
| M5 正文写作工作台与 Autosave | 未开始（符合范围） |
