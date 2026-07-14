export function FoundationPage() {
  return (
    <section className="foundation-page" aria-labelledby="foundation-title">
      <p className="section-kicker">工程基础页</p>
      <h2 id="foundation-title">AIWebNovel 前端基础已启动</h2>
      <p className="foundation-page__lead">
        当前处于阶段 0，页面仅用于确认独立前端工程已经建立。
      </p>

      <dl className="foundation-facts">
        <div>
          <dt>后端与数据基础</dt>
          <dd>数据库和后端基础已经独立建立，但尚未通过本前端连接。</dd>
        </div>
        <div>
          <dt>业务范围</dt>
          <dd>小说项目、规划、写作与评审等业务功能尚未实现。</dd>
        </div>
        <div>
          <dt>下一项集成</dt>
          <dd>前端与后端的连接将在 DEV-0.5 中建立。</dd>
        </div>
      </dl>
    </section>
  );
}
