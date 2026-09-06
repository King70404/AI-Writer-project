# 功能真实性矩阵

本文件是当前能力索引，不是路线图，也不替代逐项测试证据。M7/V1 的当前正式能力事实以 [`M7_ACCEPTANCE_REPORT.md`](M7_ACCEPTANCE_REPORT.md)、[`M7_ACCEPTANCE_CHECKLIST.md`](M7_ACCEPTANCE_CHECKLIST.md) 与 [`M7_BASELINE_MANIFEST.json`](M7_BASELINE_MANIFEST.json) 为准。

M0–M2 时期的旧细粒度 feature_id 矩阵已原样归档到 [`history/FEATURE_REALITY_MATRIX_PRE_M7.md`](history/FEATURE_REALITY_MATRIX_PRE_M7.md)。该历史矩阵继续作为当时阶段的真实性证据，但其中“尚未实现”的描述不得用于否定 M3–M7 后已经正式验收的能力。

## 当前 V1 能力索引

| 能力组 | 首次冻结/最终状态 | 当前成立的能力 | 明确限制 |
| --- | --- | --- | --- |
| Engineering foundation | M0，M7继续保留 | Windows 本地基础设施、SQLite WAL/FK、安全/诊断/启动/质量门基础 | 不代表 SaaS、多人或公网服务 |
| Project | M1，M7继续保留 | 创建、列表、读取、完整修订、不可变 Revision 历史、乐观并发 | 无删除/归档等未验收扩展 |
| Story Bible | M2，M7继续保留 | 单 Project Story Bible 创建、读取、修订、不可变历史、冲突处理 | V1 仍以已验收文本能力为准 |
| Characters | M3，M7继续保留 | 多 Character 创建、列表、读取、完整修订、不可变历史 | 无 Character relations / World graph |
| Novel Structure | M4，M7继续保留 | Outline、Volumes、Chapters，稳定对象 + immutable revisions + heads | 以 M4/M7 冻结范围为准 |
| Chapter Writing | M5，M7继续保留 | Writing Workspace、正文完整替换、Autosave、保存/冲突状态 | 无未经确认的自动覆盖 |
| Local AI Writing | M6，M7继续保留 | loopback-only OpenAI-compatible Provider、最小上下文组装、Continue / Rewrite、显式采用候选 | 无云 AI API；AI 生成本身不直接修改 Chapter |
| TXT Export / V1 loop | M7 accepted | 当前服务器已保存正文按结构导出 UTF-8 TXT；完整 V1 主闭环通过正式验收 | 不导出未保存浏览器草稿或 AI 候选；M8+ 未开始即不由 M7 授权 |

## V1 主闭环

`Project → Story Bible → Characters → Outline / Volumes / Chapters → Chapter Writing Workspace → Autosave → Local AI Continue / Rewrite → User explicit accept → Autosave → TXT Export`

## 使用规则

- 判断“当前是否已实现”时，优先看最新正式 Acceptance Report / Manifest，而不是旧阶段说明。
- 新任务如果新增或改变用户可见能力，应同时更新适用的真实性证据；不得用固定假数据、空按钮、假进度或无真实后端行为的展示声明完成。
- 本索引不自行创造新的 feature_id。需要继续维护细粒度 feature_id 时，应在后续专门任务中基于当前代码、API、路由和测试库存重新生成，而不是沿用过时的否定描述。
- 健康检查、页面可打开或单次人工演示均不能单独证明一项业务功能完成。