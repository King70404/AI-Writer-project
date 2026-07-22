import { SystemStatus } from "../components/SystemStatus";

export function FoundationPage() {
  return (
    <section
      className="foundation-page"
      data-feature-id="FND-001"
      aria-labelledby="foundation-title"
    >
      <p className="section-kicker">工程基础页</p>
      <h2 id="foundation-title">AIWebNovel 前端基础已启动</h2>
      <p className="foundation-page__lead">
        阶段 0 工程基础已冻结；当前页面继续展示可验证的本地系统状态。
      </p>

      <SystemStatus />

      <dl className="foundation-facts">
        <div>
          <dt>后端与数据基础</dt>
          <dd>状态区通过真实健康接口检查本地后端与 SQLite 基础。</dd>
        </div>
        <div>
          <dt>业务范围</dt>
          <dd>Project列表与创建已提供独立页面；规划、写作与评审尚未实现。</dd>
        </div>
        <div>
          <dt>集成范围</dt>
          <dd>当前集成仅服务工程验收，不代表小说创作能力已经实现。</dd>
        </div>
      </dl>
    </section>
  );
}
