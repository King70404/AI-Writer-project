import { useEffect, useState } from "react";

import {
  checkBackendHealth,
  type BackendHealthCheckOptions,
  type BackendHealthResult,
  type BackendNotReadyReason,
} from "../api/health";

type SystemStatusState =
  | { readonly kind: "checking" }
  | { readonly kind: "ready" }
  | {
      readonly kind: "backend_not_ready";
      readonly reason: BackendNotReadyReason;
    }
  | { readonly kind: "backend_unavailable" };

export interface SystemStatusProps {
  readonly checkHealth?: (
    options: BackendHealthCheckOptions,
  ) => Promise<BackendHealthResult>;
}

const NOT_READY_REASON: Readonly<Record<BackendNotReadyReason, string>> = {
  configuration: "后端配置检查未通过。",
  application: "后端应用检查未通过。",
  database: "数据库基础检查未通过。",
  frontend: "前端构建检查未通过。",
  readiness: "未能确认后端就绪状态。",
};

function statusContent(state: SystemStatusState) {
  switch (state.kind) {
    case "checking":
      return <p>正在检查本地后端状态。</p>;
    case "ready":
      return <p>本地后端已连接，数据库基础检查通过。</p>;
    case "backend_not_ready":
      return (
        <>
          <p>本地后端可访问，但尚未就绪。</p>
          <p className="system-status__reason">
            {NOT_READY_REASON[state.reason]}
          </p>
        </>
      );
    case "backend_unavailable":
      return <p>当前无法连接本地后端。</p>;
  }
}

export function SystemStatus({
  checkHealth = checkBackendHealth,
}: SystemStatusProps) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<SystemStatusState>({ kind: "checking" });

  useEffect(() => {
    const controller = new AbortController();
    let current = true;

    void checkHealth({ signal: controller.signal })
      .then((result) => {
        if (!current || controller.signal.aborted) {
          return;
        }
        setState(
          result.kind === "ready"
            ? { kind: "ready" }
            : {
                kind: "backend_not_ready",
                reason: result.reason,
              },
        );
      })
      .catch(() => {
        if (current && !controller.signal.aborted) {
          setState({ kind: "backend_unavailable" });
        }
      });

    return () => {
      current = false;
      controller.abort();
    };
  }, [attempt, checkHealth]);

  const checking = state.kind === "checking";
  const recheck = () => {
    if (checking) {
      return;
    }
    setState({ kind: "checking" });
    setAttempt((currentAttempt) => currentAttempt + 1);
  };

  return (
    <section
      className="system-status"
      data-feature-id="FND-002"
      data-state={state.kind}
      aria-labelledby="system-status-title"
      aria-busy={checking}
    >
      <div>
        <p className="section-kicker">真实基础检查</p>
        <h3 id="system-status-title">本地系统状态</h3>
      </div>
      <div
        className="system-status__message"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        {statusContent(state)}
      </div>
      <button
        type="button"
        data-feature-id="FND-003"
        onClick={recheck}
        disabled={checking}
      >
        重新检查
      </button>
    </section>
  );
}
