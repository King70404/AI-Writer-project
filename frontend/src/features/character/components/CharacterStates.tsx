import type { CharacterApiError } from "../api/errors";

export function CharacterLoading({ message = "正在读取角色…" }) {
  return (
    <p role="status" aria-live="polite">
      {message}
    </p>
  );
}

export function CharacterAlert({
  title,
  message,
  onRetry,
}: {
  readonly title: string;
  readonly message: string;
  readonly onRetry?: () => void;
}) {
  return (
    <section className="character-alert" role="alert">
      <h3>{title}</h3>
      <p>{message}</p>
      {onRetry === undefined ? null : (
        <button type="button" onClick={onRetry}>
          重新尝试
        </button>
      )}
    </section>
  );
}

export function CharacterErrorAlert({
  error,
  onRetry,
}: {
  readonly error: CharacterApiError;
  readonly onRetry?: () => void;
}) {
  return (
    <CharacterAlert
      title="角色请求未完成"
      message={error.message}
      onRetry={onRetry}
    />
  );
}
