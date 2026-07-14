import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <section className="not-found-page" aria-labelledby="not-found-title">
      <p className="section-kicker">404</p>
      <h2 id="not-found-title">页面不存在</h2>
      <p>该地址不属于当前阶段的前端基础范围。</p>
      <Link className="text-link" to="/">
        返回基础页
      </Link>
    </section>
  );
}
