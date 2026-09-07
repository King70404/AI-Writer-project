# 功能真实性矩阵

本文件是当前能力索引，不是路线图，也不替代逐项测试证据。M7/V1 的正式冻结基线仍以 [`M7_ACCEPTANCE_REPORT.md`](M7_ACCEPTANCE_REPORT.md)、[`M7_ACCEPTANCE_CHECKLIST.md`](M7_ACCEPTANCE_CHECKLIST.md) 与 [`M7_BASELINE_MANIFEST.json`](M7_BASELINE_MANIFEST.json) 为准；M7 之后经单独任务验收的可用性增强在本表中单独说明，不移动 M0–M7 标签。

M0–M2 时期的旧细粒度 feature_id 矩阵已原样归档到 [`history/FEATURE_REALITY_MATRIX_PRE_M7.md`](history/FEATURE_REALITY_MATRIX_PRE_M7.md)。该历史矩阵继续作为当时阶段的真实性证据，但其中“尚未实现”的描述不得用于否定 M3–M7 后已经正式验收的能力。

## 当前 V1 能力索引

| 能力组 | 首次冻结/最终状态 | 当前成立的能力 | 明确限制 |
| --- | --- | --- | --- |
| Engineering foundation | M0，M7继续保留 | Windows 本地基础设施、SQLite WAL/FK、安全/诊断/启动/质量门基础；普通作者可使用根目录双击启动入口 | 不代表 SaaS、多人或公网服务 |
| Project | M1，M7继续保留；V1-UX-1 增强 | 创建、列表、读取、完整修订、不可变 Revision 历史、乐观并发；普通作者界面隐藏内部 ID/并发字段；支持带书名确认的逻辑删除 | 删除为不可逆的普通界面移除，不暴力擦除冻结的不可变 Revision 历史；归档/恢复未实现 |
| Story Bible | M2，M7继续保留；V1-UX-1 文案增强 | 单 Project 小说设定创建、读取、修订、不可变历史、冲突处理 | V1 仍以已验收文本能力为准 |
| Characters | M3，M7继续保留；V1-UX-1 输入体验增强 | 多 Character 创建、列表、读取、完整修订、不可变历史；创作文本框关闭浏览器历史自动提示 | 无 Character relations / World graph |
| Novel Structure | M4，M7继续保留 | Outline、Volumes、Chapters，稳定对象 + immutable revisions + heads | 以 M4/M7 冻结范围为准 |
| Chapter Writing | M5，M7继续保留 | Writing Workspace、正文完整替换、Autosave、保存/冲突状态 | 无未经确认的自动覆盖 |
| Local AI Writing | M6，M7继续保留 | loopback-only OpenAI-compatible Provider、最小上下文组装、Continue / Rewrite、显式采用候选 | 当前冻结 V1 无云 AI API；云 Provider 属于后续 V1-AI-1 |
| TXT Export / V1 loop | M7 accepted | 当前服务器已保存正文按结构导出 UTF-8 TXT；完整 V1 主闭环通过正式验收 | 不导出未保存浏览器草稿或 AI 候选；M8+ 未开始即不由 M7 授权 |

## V1 主闭环

`小说 → 小说设定 → 人物 → 大纲 / 分卷 / 章节 → 章节正文 → Autosave → AI Continue / Rewrite → 用户显式采用 → Autosave → TXT 导出`

## 使用规则

- 判断“当前是否已实现”时，优先看最新正式 Acceptance Report / Manifest 与后续已经验收的编号任务，而不是旧阶段说明。
- 新任务如果新增或改变用户可见能力，应同时更新适用的真实性证据；不得用固定假数据、空按钮、假进度或无真实后端行为的展示声明完成。
- 本索引不自行创造新的 feature_id。需要继续维护细粒度 feature_id 时，应在后续专门任务中基于当前代码、API、路由和测试库存重新生成，而不是沿用过时的否定描述。
- 健康检查、页面可打开或单次人工演示均不能单独证明一项业务功能完成。