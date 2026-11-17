import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  budgetClient as defaultBudgetClient,
  MODE_LABELS,
  REASON_LABELS,
  type BudgetClient,
  type SendEstimate,
} from "../api/budget";

/**
 * 发送前预估（B2）。读取预估不调用模型。严格预算由本机服务在发送时再检查一次；
 * 本面板只负责让作者在确认发送前看到上限与预算结论：严格模式拒绝时禁止发送，
 * 提示模式超出时需作者额外勾选确认。
 */
export function SendEstimatePanel({
  chapterId,
  runId,
  refreshKey,
  onGate,
  client = defaultBudgetClient,
}: {
  readonly chapterId: string;
  readonly runId: string;
  /** 任务步骤或候选变化时重新预估（父组件同时以它作 key 重置本组件）。 */
  readonly refreshKey: string;
  /** 是否允许发送：严格拒绝或未确认的提示为 false。 */
  readonly onGate: (allowed: boolean, reason: string) => void;
  readonly client?: BudgetClient;
}) {
  const loadEstimate = useCallback(
    () => client.estimate(chapterId, runId),
    [chapterId, client, runId],
  );
  return (
    <OperationEstimatePanel
      key={`${chapterId}:${runId}:${refreshKey}`}
      loadEstimate={loadEstimate}
      refreshKey={refreshKey}
      onGate={onGate}
    />
  );
}

export function OperationEstimatePanel({
  loadEstimate,
  refreshKey,
  onGate,
}: {
  readonly loadEstimate: () => Promise<SendEstimate>;
  readonly refreshKey: string;
  readonly onGate: (allowed: boolean, reason: string) => void;
}) {
  const [estimate, setEstimate] = useState<SendEstimate | null>(null);
  const [failed, setFailed] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const refresh = () => {
    setFailed(false);
    setEstimate(null);
    setAcknowledged(false);
    setAttempt((value) => value + 1);
  };
  useEffect(() => {
    let alive = true;
    loadEstimate()
      .then((value) => {
        if (alive) setEstimate(value);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, [loadEstimate, refreshKey, attempt]);
  const decision = estimate?.decision;
  useEffect(() => {
    if (!estimate || failed) onGate(false, "请先完成发送前预估，再确认发送。");
    else if (decision === "refused")
      onGate(
        false,
        "按你设定的严格预算，本次不会发送。可调整预算或价格后重新预估。",
      );
    else if (decision === "warning" && !acknowledged)
      onGate(false, "预估可能超出预算，请先勾选确认后再发送。");
    else onGate(true, "");
  }, [acknowledged, decision, estimate, failed, onGate]);
  useEffect(() => () => onGate(true, ""), [onGate]);
  if (failed)
    return (
      <div className="send-estimate">
        <p>暂时无法读取发送前预估；请重新预估后再确认发送。</p>
        <button type="button" onClick={refresh}>
          重新预估
        </button>
      </div>
    );
  if (!estimate)
    return (
      <p className="send-estimate" role="status">
        正在计算发送前预估…
      </p>
    );
  const reasons = estimate.reasons.map((reason) => REASON_LABELS[reason]);
  return (
    <section aria-label="发送前预估" className="send-estimate">
      <button type="button" onClick={refresh}>
        重新预估
      </button>
      <p>
        发送前预估（保守上限，不是账单）：输入不超过{" "}
        {estimate.input_tokens_upper} token（按 UTF-8 字节数估算，本机字符{" "}
        {estimate.input_characters}），输出不超过 {estimate.output_tokens_upper}{" "}
        token（模型配置的输出上限）。
      </p>
      <p>
        {estimate.price && estimate.estimated_cost_upper
          ? `按你填写的价格（每百万 token 输入 ${estimate.price.input_per_million} / 输出 ${estimate.price.output_per_million} ${estimate.price.currency}），本次最多约 ${estimate.estimated_cost_upper} ${estimate.price.currency}。服务商实际账单以其计费为准。`
          : "未计价：当前模型未填写价格，不估算金额。"}
      </p>
      {estimate.budget_mode === "off" ? (
        <p>本书未设预算。</p>
      ) : (
        <p>
          本书预算：{MODE_LABELS[estimate.budget_mode]}。
          {estimate.task_limit
            ? `单任务上限 ${estimate.task_limit} ${estimate.budget_currency}，本任务已用（含待确认）${estimate.task_spent_upper} ${estimate.budget_currency}；`
            : ""}
          {estimate.monthly_limit
            ? `本月上限 ${estimate.monthly_limit} ${estimate.budget_currency}，本月已用（含待确认）${estimate.month_spent_upper} ${estimate.budget_currency}。`
            : ""}
          {estimate.unpriced_attempts
            ? ` 另有 ${estimate.unpriced_attempts} 次请求发生在填写价格前，金额未知，未按 0 计。`
            : ""}
        </p>
      )}
      {estimate.decision === "refused" ? (
        <p role="alert">按严格预算不会发送：{reasons.join("；")}。</p>
      ) : null}
      {estimate.decision === "warning" ? (
        <div role="alert">
          <p>预算提示：{reasons.join("；")}。</p>
          <label>
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(event) => setAcknowledged(event.target.checked)}
            />
            我已知晓可能超出预算，仍要发送这一次
          </label>
        </div>
      ) : null}
    </section>
  );
}

export function OperationSendGuard({
  loadEstimate,
  refreshKey,
  children,
}: {
  readonly loadEstimate: () => Promise<SendEstimate>;
  readonly refreshKey: string;
  readonly children: (allowed: boolean) => ReactNode;
}) {
  const [allowed, setAllowed] = useState(false);
  const onGate = useCallback((value: boolean) => setAllowed(value), []);
  return (
    <>
      <OperationEstimatePanel
        loadEstimate={loadEstimate}
        refreshKey={refreshKey}
        onGate={onGate}
      />
      {children(allowed)}
    </>
  );
}
