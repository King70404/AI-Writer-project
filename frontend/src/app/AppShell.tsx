import { NavLink, Outlet } from "react-router";

export function AppShell() {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        跳至主要内容
      </a>
      <header className="app-shell__header">
        <div>
          <p className="app-shell__eyebrow">本地长篇创作</p>
          <h1 className="app-shell__title">AI 网文助手</h1>
        </div>
        <nav className="app-navigation" aria-label="主要导航">
          <NavLink to="/" end>
            首页
          </NavLink>
          <NavLink to="/projects">书架</NavLink>
          <NavLink to="/backups">数据备份</NavLink>
        </nav>
      </header>

      <main className="app-shell__main" id="main-content" tabIndex={-1}>
        <Outlet />
      </main>

      <footer className="app-shell__footer">
        <p>
          <span className="phase-label" aria-label="当前版本：V1">
            V1
          </span>{" "}
          本机保存小说、设定、人物、卷章与正文修订，可导出 TXT。AI
          生成的候选只有在作者确认后才会写入正文。
        </p>
      </footer>
    </div>
  );
}
