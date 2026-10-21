import { NavLink, Outlet } from "react-router";

export function AppShell() {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        跳至主要内容
      </a>
      <header className="app-shell__header">
        <div>
          <p className="app-shell__eyebrow">本地长篇创作系统 · V1</p>
          <h1 className="app-shell__title">AIWebNovel</h1>
        </div>
        <p className="phase-label" aria-label="当前版本：V1">
          V1
        </p>
      </header>

      <nav className="app-navigation" aria-label="主要导航">
        <NavLink to="/" end>
          工程基础
        </NavLink>
        <NavLink to="/projects">项目</NavLink>
        <NavLink to="/backups">数据备份</NavLink>
      </nav>

      <main className="app-shell__main" id="main-content" tabIndex={-1}>
        <Outlet />
      </main>

      <footer className="app-shell__footer">
        <p>
          V1 支持项目、设定、人物、小说结构、章节写作与 TXT 导出。 AI
          协作支持配置本地或云端模型，候选由作者确认后采纳。
        </p>
      </footer>
    </div>
  );
}
