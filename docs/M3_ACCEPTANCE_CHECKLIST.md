# M3 Character 基础能力验收清单

本清单中的“通过”只表示证据符合 M3 冻结范围；明确未实现项是 scope boundary，不是已完成能力。

| Check | Evidence | Result |
| --- | --- | --- |
| 实现基线 | HEAD `8864938d1389f9900299f5dc7095d7a1f9f058b9`，tree `27a3a29950e1d365dac87822366965db9aaa0012`，40 commits，598 tracked files | 通过 |
| Git 起始状态 | `main`；worktree、staging、remote 均为空 | 通过 |
| M0/M1/M2 冻结 | 三个 annotated tag 身份不变；九份旧冻结文件相对各自 tag 无差异 | 通过 |
| M3 实现链 | 11 个规定提交顺序、完整哈希与主题一致，含 Q8 与 Q10 稳定化提交 | 通过 |
| Character 领域 | stable object、immutable revisions、head authority、prefixed ULID、optimistic concurrency | 通过 |
| Character 持久化 | 三表、事务 Repository、Head CAS、Revision 不可变、失败回滚 | 通过 |
| Character 应用层 | Create/Revise/Get/List/History 用例、不可变 Snapshot、显式映射与严格副作用顺序 | 通过 |
| Character HTTP | create、list、read、update、ETag/If-Match、只读历史列表与详情 | 通过 |
| Character 前端 | Project 内列表、创建、编辑、冲突恢复及不可变历史查看 | 通过 |
| 历史分页 | Character-bound 严格 Keyset cursor；摘要不含完整 profile；详情按需返回 profile | 通过 |
| 继承能力 | PRJ-001..007 与 STB-001..003 无回归 | 通过 |
| Feature IDs | 精确为 PRJ-001..007、STB-001..003、CHR-001..003 | 通过 |
| 后端质量 | 2268 tests；statements 96.85%；branches 92.57% | 通过 |
| 前端质量 | 43 files、473 tests；2369/2469 statements，2308/2525 branches，539/544 functions，2328/2416 lines；90 coverage files | 通过 |
| ESLint 边界门 | 27 samples、12 carrier groups、1 ESLint、1 config calculation、1 Linter、12 verify、0 disk writes、15000ms；三种顺序诊断一致 | 通过 |
| E2E 库存 | development 3、integration 16、missing-build 1，共 20 | 通过 |
| 重点 E2E | INT-008、010、014、015、016 均通过 | 通过 |
| 六次正式质量门 | 文档前与暂存后各执行 Default、IncludeE2E、Audit+E2E；六次均 exit 0 | 通过 |
| 四次正式 E2E | 四个 IncludeE2E 套件均 20/20 | 通过 |
| 依赖审计 | 两次 npm production audit 均为 0 漏洞；React Router 8.3.0 | 通过 |
| Production API | 实际 OpenAPI 精确 21 operations；Character 历史仅 GET | 通过 |
| Frontend routes | 10 个带 path 路由，无 path 布局不计数 | 通过 |
| Metadata | 9 表，只有 Project、Story Bible、Character 三组三表 | 通过 |
| Alembic | head `0004_create_character_foundation`，不存在 0005 | 通过 |
| Migration blobs | 0001/0002/0003/0004 分别为任务冻结的 4 个精确 Git blob | 通过 |
| Revision triggers | 实际迁移 SQLite 中 6 个 no-update/no-delete 触发器 | 通过 |
| Q8 事实 | INT-010 等待精确 URL、`.project-edit` 与输入状态，保留 `toBeFocused()`；仅测试稳定化 | 通过 |
| Q10 事实 | INT-008 声明卸载导致的单个预期 health cancellation；仅测试生命周期/browser audit 稳定化 | 通过 |
| DEV-001 观察 | H / 未定位 / 当前未复现 / 未证明已修复 | 通过 |
| Story Bible 观察 | 历史 timeout 当前未复现；未修改代码/测试/timeout，未增加 sleep/retry，不宣称已修复 | 通过 |
| 诊断工具边界 | 仓库外进程观察工具未加入仓库、产品或生产 runtime | 通过 |
| 安全隐私 | local-first、single-user、127.0.0.1、本地 SQLite、WAL/FK；无云凭据、遥测、remote 或 push | 通过 |
| 架构 | Python/FastAPI/SQLite/SQLAlchemy/Alembic 模块化单体；React/TypeScript/Vite/React Router 前端 | 通过 |
| 文件范围 | 只新增三份 M3 验收文件；无产品、测试、配置或依赖变化 | 通过 |
| 文档格式 | UTF-8、LF、final newline；Manifest 为 strict JSON；无绝对本机路径或凭据 | 通过 |
| Character 删除/归档/恢复/diff/rollback | scope boundary / unimplemented | 未实现（符合范围） |
| Historical Character write/delete/adopt | scope boundary / unimplemented | 未实现（符合范围） |
| Relationships 与扩展设定 | Character relationships、World、Location、Organization、Power systems、Abilities、Items 均为 scope boundary | 未实现（符合范围） |
| 扩展字段与附件 | structured age/gender/alignment、Avatar、Attachments、Markdown/rich text 为 scope boundary | 未实现（符合范围） |
| 写作与 AI | Outline、Volume、Chapter、AI generation、Agents、Skills、Prompts 为 scope boundary | 未实现（符合范围） |
| 自动保存与发布 | Autosave、browser draft persistence、cloud API、remote Git、release、publishing 为 scope boundary | 未实现（符合范围） |
| 后续迁移与阶段 | 不存在 0005；M4 未启动 | 未实现（符合范围） |
| 冻结提交与标签 | Acceptance commit 仅含三份文档；annotated `m3-character-foundation` 指向该提交 | 通过 |
| 最终状态 | 41 commits；worktree、staging、remote 均为空；临时资源清理完成 | 通过 |
