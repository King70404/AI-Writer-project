import { Link } from "react-router";

import { SystemStatus } from "../components/SystemStatus";

export function FoundationPage() {
  return (
    <section
      className="foundation-page"
      data-feature-id="FND-001"
      aria-labelledby="foundation-title"
    >
      <p className="section-kicker">V1 本地创作入口</p>
      <h2 id="foundation-title">AIWebNovel 前端基础已启动</h2>
      <p className="foundation-page__lead">
        从项目开始：建立设定与人物，创建卷和章节，写正文并自动保存，最后导出整本小说。
      </p>
      <p>
        <Link to="/projects">开始使用：进入项目</Link>
      </p>

      <SystemStatus />

      <dl className="foundation-facts">
        <div>
          <dt>后端与数据基础</dt>
          <dd>状态区通过真实健康接口检查本地后端与 SQLite 基础。</dd>
        </div>
        <div>
          <dt>业务范围</dt>
          <dd>
            项目内可管理设定、人物与小说结构，进入章节写作工作台并导出 TXT。
          </dd>
        </div>
        <div>
          <dt>集成范围</dt>
          <dd>本地 AI 未配置时，手动写作、自动保存与导出仍可使用。</dd>
        </div>
      </dl>
    </section>
  );
}
