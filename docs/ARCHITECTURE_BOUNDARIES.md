# 架构边界

本文档仅记录 AIWebNovel 的高层模块边界和交互约束，不创建或代表任何实现代码。

## 业务模块

- Project
- Market
- StoryBible
- Planning
- Writing
- Review
- Canon
- Style
- Analytics
- Workflow

## 基础设施模块

- Assets
- Search
- CodexRuntime
- Infrastructure

## 所有权与跨模块规则

- 每类数据只能有一个权威所有者，其他模块不得绕过所有者直接读写其内部存储。
- 跨模块调用只能通过公开应用服务并使用版本化 DTO；需要跨模块传播的领域变化使用持久化领域事件。
- 模块内部 Repository、数据库表和实现细节不属于公开契约。

## 明确禁止

- Writing 不得直接写入 Canon。
- Review 不得直接修改正文。
- Planning 不得直接修改正式状态或正式事实。
- Style 不得直接修改正文。
- Market 或 Analytics 不得自动改变正式项目。
- Workflow 不得直接写业务表，必须通过公开应用服务编排业务操作。
- CodexRuntime 不得访问业务 Repository。
- Search 只用于召回，不是正式事实来源。
- UI 不得直接访问 SQLite，必须通过后端公开接口与应用服务访问业务能力。
