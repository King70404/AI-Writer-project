import { Component, type ErrorInfo, type ReactNode } from "react";

interface AppErrorBoundaryProps {
  readonly children: ReactNode;
  readonly onReload?: () => void;
}

interface AppErrorBoundaryState {
  readonly hasError: boolean;
}

export class AppErrorBoundary extends Component<
  AppErrorBoundaryProps,
  AppErrorBoundaryState
> {
  public state: AppErrorBoundaryState = { hasError: false };

  public static getDerivedStateFromError(): AppErrorBoundaryState {
    return { hasError: true };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    if (import.meta.env.DEV) {
      console.error("React 渲染发生未处理错误。", error, errorInfo);
    }
  }

  private readonly reloadCurrentPage = (): void => {
    if (this.props.onReload !== undefined) {
      this.props.onReload();
      return;
    }

    window.location.reload();
  };

  public render(): ReactNode {
    if (this.state.hasError) {
      return (
        <main className="error-fallback">
          <h1>页面暂时无法显示</h1>
          <p>前端遇到了意外问题。请重新加载当前页面后再试。</p>
          <button type="button" onClick={this.reloadCurrentPage}>
            重新加载当前页面
          </button>
        </main>
      );
    }

    return this.props.children;
  }
}
