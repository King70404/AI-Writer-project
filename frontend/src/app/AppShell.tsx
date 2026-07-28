import { NavLink, Outlet } from "react-router";

export function AppShell() {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        跳至主要内容
      </a>
      <header className="app-shell__header">
        <div>
          <p className="app-shell__eyebrow">本地长篇创作系统 · 工程基础</p>
          <h1 className="app-shell__title">AIWebNovel</h1>
        </div>
        <p className="phase-label" aria-label="当前阶段：阶段 2">
          阶段 2
        </p>
      </header>

      <nav className="app-navigation" aria-label="主要导航">
        <NavLink to="/" end>
          工程基础
        </NavLink>
        <NavLink to="/projects">项目</NavLink>
      </nav>

      <main className="app-shell__main" id="main-content" tabIndex={-1}>
        <Outlet />
      </main>

      <footer className="app-shell__footer">
        <p>
          当前状态：Project基础与单份纯文本Story
          Bible流程已实现；规划、章节写作与AI功能尚未实现。
        </p>
      </footer>
    </div>
  );
}
