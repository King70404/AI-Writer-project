interface LoadingStateProps {
  readonly message?: string;
}

export function LoadingState({
  message = "正在准备内容，请稍候。",
}: LoadingStateProps) {
  return (
    <div className="loading-state" role="status" aria-live="polite">
      <span className="loading-state__mark" aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}
