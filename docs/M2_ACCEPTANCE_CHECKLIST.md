# M2 Story Bible基础能力正式验收清单

以下项目均由DEV-2.7本次执行的Git核验、专项测试或完整质量门证据确认。

## Git与冻结基线

- [x] 执行前HEAD精确为`2e28d41a304a80ad9544dfea7558ae4c05563ca1`，提交总数28，分支`main`且工作区干净。
- [x] M0 annotated tag对象、目标及三份冻结文件未变化。
- [x] M1 annotated tag对象、目标、消息及三份冻结文件未变化。
- [x] 执行前不存在`m2-story-bible-foundation`。
- [x] M2范围与明确未完成范围准确，没有新增功能真实性ID。

## 领域与持久化

- [x] Story Bible领域ID、Title、Content和值对象规则通过。
- [x] Stable Object、Revision、Head与Aggregate不变量通过。
- [x] 初始Revision/Version为1，追加严格递增并采用完整替换。
- [x] 旧Aggregate与旧Revision保持不可变。
- [x] Story Bible只单向归属Project。
- [x] 三张Story Bible表和Project三表组成精确六表Metadata。
- [x] 一个Project至多一个Story Bible的唯一约束有效。
- [x] Migration 0003及`0001→0002→0003→0002→0003`循环通过。
- [x] 两个Story Bible Revision不可变触发器有效；两个Project Revision触发器保持有效。
- [x] Repository原子事务、失败回滚和数据损坏处理通过。
- [x] Stable Object CAS与Head CAS均有效。
- [x] 双实例并发恰好一成功一冲突，无锁错误或自动重试。

## 应用、HTTP与前端

- [x] Create/Revise应用命令字段精确且不可变。
- [x] Get/GetForProject应用查询字段精确且不可变。
- [x] 应用Snapshot只含原语，显式映射且脱离ORM。
- [x] 创建副作用顺序、单次Repository调用和无预查询通过。
- [x] 修订副作用顺序、单次Repository调用、无预查询及Repository内Clock/Factory责任通过。
- [x] 4条Story Bible当前资源API通过。
- [x] 2条Story Bible历史API通过。
- [x] 强ETag与If-Match协议通过。
- [x] 缺失If-Match返回428，非法If-Match返回400，stale返回412。
- [x] POST/PUT的Session、CSRF和可信Origin保护通过。
- [x] 未迁移数据库安全503且不自动迁移。
- [x] 前端真实创建与修订流程通过。
- [x] 409与写结果未知均保留输入并要求显式核实。
- [x] 412保留草稿与旧baseline，不自动GET、重试或合并。

## 不可变历史

- [x] 历史Reader与写Repository分离。
- [x] Head是当前Revision唯一权威，不使用最大RevisionNumber替代。
- [x] RevisionNumber降序Keyset分页、20+1和`limit + 1`语义通过。
- [x] cursor严格、规范并绑定Story Bible。
- [x] 历史列表不读取正文，不使用COUNT或OFFSET。
- [x] 单Revision正文按需读取。
- [x] 历史Revision不可编辑、删除、回滚或恢复。
- [x] 前端历史路由、分页、current标记、失败保留与竞态保护通过。

## 安全、质量与真实性

- [x] 正文、草稿、ETag、cursor和选择项不进入浏览器持久化。
- [x] 日志不记录Session、CSRF、If-Match、ETag、cursor、正文或草稿。
- [x] 后端1655项测试通过，statements 95.99%、branches 90.66%。
- [x] 前端36个文件354项测试通过，statements 96.26%、branches 91.85%、functions 99.45%、lines 96.28%。
- [x] Story Bible历史后端专项135项通过，statements/branches均100%。
- [x] Story Bible历史前端专项24项通过，96.03%/91.30%/100%/96.03%。
- [x] 17个E2E全部通过。
- [x] 默认、IncludeE2E、依赖审计加IncludeE2E三种完整质量门全部通过。
- [x] npm生产依赖审计为0漏洞，React Router为8.3.0。
- [x] 任务专属临时根、SQLite sidecar、Playwright产物、服务和端口已清理。
- [x] PRJ-001至PRJ-007与STB-001至STB-003保持精确，没有STB-004。
- [x] 未创建Character、World、PowerSystem、规划、章节、Codex、Agent或M3功能。
- [x] 提交前后均无Git remote，未推送。
- [x] M2验收提交后工作区干净，提交总数29。
- [x] `m2-story-bible-foundation`创建为annotated tag并指向验收提交。

## 冻结政策

- [x] M2标签不得移动、覆盖或重建。
- [x] 三份M2验收文件未来不得改写。
- [x] 后续扩展和缺陷修复必须使用新编号任务与新提交，不得amend或改写M2历史事实。
- [x] M0、M1标签和六份既有冻结文件继续永久保留。
- [x] M2冻结只代表Story Bible基础闭环，不代表完整AI网文产品完成。
