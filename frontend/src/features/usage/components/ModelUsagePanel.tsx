import { useEffect, useRef, useState } from "react";
import { collectUsage, downloadUsageCsv, usageCsv } from "../api/usage-csv";

import {
  OPERATION_LABELS,
  STATUS_LABELS,
  usageClient,
  usageError,
  type UsageAttempt,
  type UsageClient,
  type UsagePage,
  type UsageTotals,
} from "../api/usage";

const PAGE = 10;

function n(value: number): string {
  return value.toLocaleString("zh-CN");
}

function tokens(value: number | null): string {
  return value === null ? "未报告" : n(value);
}

function TotalsView({ totals }: { readonly totals: UsageTotals }) {
  const states = [
    totals.completed ? `已返回 ${n(totals.completed)}` : "",
    totals.failed ? `失败 ${n(totals.failed)}` : "",
    totals.timeout ? `超时 ${n(totals.timeout)}` : "",
    totals.interrupted ? `中断 ${n(totals.interrupted)}` : "",
    totals.running ? `进行中 ${n(totals.running)}` : "",
  ].filter(Boolean);
  return (
    <dl className="model-usage__totals">
      <dt>已发出的模型请求</dt>
      <dd>
        {n(totals.attempts)} 次
        {states.length ? `（${states.join(" · ")}）` : ""}
      </dd>
      <dt>服务商报告的 token</dt>
      <dd>
        {totals.reported_attempts
          ? `输入 ${n(totals.reported_input_tokens)} · 输出 ${n(totals.reported_output_tokens)}（来自 ${n(totals.reported_attempts)} 次报告${
              totals.incomplete_reports
                ? `，其中 ${n(totals.incomplete_reports)} 次只报告了部分数值`
                : ""
            }）`
          : "无报告"}
      </dd>
      <dt>用量未知</dt>
      <dd>
        {n(totals.unknown_attempts)} 次
        {totals.unknown_attempts ? "（未计入上方 token 合计，不按 0 计）" : ""}
      </dd>
      <dt>本机字符计数（估算依据，不是 token）</dt>
      <dd>
        发送 {n(totals.input_characters)} 字符 · 返回{" "}
        {n(totals.output_characters)} 字符
      </dd>
    </dl>
  );
}

function AttemptRow({ item }: { readonly item: UsageAttempt }) {
  const when = new Date(item.started_at);
  const time = Number.isNaN(when.getTime())
    ? item.started_at
    : when.toLocaleString("zh-CN", { hour12: false });
  return (
    <li>
      <span>
        {time} · {OPERATION_LABELS[item.operation]} · {item.model_name}
        {item.model_kind === "cloud" ? "（云端）" : "（本机）"} ·{" "}
        {STATUS_LABELS[item.status]}
      </span>
      <span>
        {item.usage_source === "provider_reported"
          ? `服务商报告：输入 ${tokens(item.reported_input_tokens)} · 输出 ${tokens(item.reported_output_tokens)} token`
          : "用量未知（服务商未报告）"}
        {" · "}发送 {n(item.input_characters)} 字符
        {item.output_characters === null
          ? ""
          : ` · 返回 ${n(item.output_characters)} 字符`}
        {item.duration_ms === null
          ? ""
          : ` · 耗时 ${(item.duration_ms / 1000).toFixed(1)} 秒`}
      </span>
    </li>
  );
}

type Result =
  | { readonly key: string; readonly status: "error"; readonly message: string }
  | {
      readonly key: string;
      readonly status: "ready";
      readonly page: UsagePage;
    };

/**
 * 模型用量面板（B1）：打开时才读取台账，查看与刷新都不调用模型。
 * 只显示服务商报告的 token、未知次数与本机字符计数；不估算金额（价格与预算属 B2）。
 */
export function ModelUsagePanel({
  projectId,
  chapterId,
  title,
  refreshKey = 0,
  client = usageClient,
}: {
  readonly projectId: string;
  readonly chapterId?: string;
  readonly title: string;
  /** 变化时（例如一次生成结束）若面板已打开则重新读取。 */
  readonly refreshKey?: number | string;
  readonly client?: UsageClient;
}) {
  const [open, setOpen] = useState(false);
  const [reloads, setReloads] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const [more, setMore] = useState<{
    readonly key: string;
    readonly items: readonly UsageAttempt[];
    readonly next: number | null;
    readonly loading: boolean;
    readonly error: string;
  }>({ key: "", items: [], next: null, loading: false, error: "" });
  const key = `${projectId}:${chapterId ?? ""}:${String(refreshKey)}:${reloads}`;
  const current = useRef(key);
  useEffect(() => {
    current.current = key;
  }, [key]);

  useEffect(() => {
    if (!open) return undefined;
    const controller = new AbortController();
    client
      .page(projectId, { chapterId, limit: PAGE }, controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return;
        setResult({ key, status: "ready", page });
        setMore({
          key,
          items: page.items,
          next: page.next_offset,
          loading: false,
          error: "",
        });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setResult({ key, status: "error", message: usageError(error).message });
      });
    return () => controller.abort();
  }, [chapterId, client, key, open, projectId]);

  const reload = () => setReloads((value) => value + 1);
  const [exporting, setExporting] = useState({ busy: false, error: "" });
  const exportCsv = () => {
    if (exporting.busy) return;
    setExporting({ busy: true, error: "" });
    collectUsage(client, projectId, chapterId)
      .then((items) => {
        downloadUsageCsv(usageCsv(items));
        setExporting({ busy: false, error: "" });
      })
      .catch((error: unknown) => {
        setExporting({
          busy: false,
          error:
            error instanceof Error && error.name === "UsageExportTooLarge"
              ? error.message
              : usageError(error).message,
        });
      });
  };
  const state =
    !open || result === null || result.key !== key
      ? ({ status: open ? "loading" : "idle" } as const)
      : result;

  const loadMore = () => {
    if (more.next === null || more.loading) return;
    const token = key;
    setMore((previous) => ({ ...previous, loading: true, error: "" }));
    client
      .page(projectId, { chapterId, offset: more.next, limit: PAGE })
      .then((page) => {
        if (token !== current.current) return;
        setMore((previous) => ({
          key: token,
          items: [...previous.items, ...page.items],
          next: page.next_offset,
          loading: false,
          error: "",
        }));
      })
      .catch((error: unknown) => {
        if (token !== current.current) return;
        setMore((previous) => ({
          ...previous,
          loading: false,
          error: usageError(error).message,
        }));
      });
  };

  return (
    <details
      className="model-usage"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>{title}</summary>
      <p className="model-usage__note">
        只记录已经发出的模型请求。“服务商报告”取自模型响应；服务商未报告、请求失败、超时或中断时记为“未知”，不按
        0 计。字符数是本机计数，不是 token，也不是账单；未设置价格，不估算金额。
      </p>
      {state.status === "loading" ? (
        <p role="status">正在读取模型用量…</p>
      ) : null}
      {state.status === "error" ? (
        <div role="alert">
          <p>{state.message}</p>
          <button type="button" onClick={reload}>
            重试
          </button>
        </div>
      ) : null}
      {state.status === "ready" ? (
        <>
          {state.page.totals.attempts === 0 ? (
            <p>还没有发出过模型请求。</p>
          ) : (
            <>
              <TotalsView totals={state.page.totals} />
              {state.page.by_operation.length > 1 ? (
                <ul className="model-usage__groups" aria-label="按操作汇总">
                  {state.page.by_operation.map((group) => (
                    <li key={group.operation}>
                      {OPERATION_LABELS[group.operation]}：
                      {n(group.totals.attempts)} 次，报告输出{" "}
                      {n(group.totals.reported_output_tokens)} token，未知{" "}
                      {n(group.totals.unknown_attempts)} 次
                    </li>
                  ))}
                </ul>
              ) : null}
              <h5>最近的请求</h5>
              <ol className="model-usage__items" aria-label="模型请求记录">
                {more.items.map((item) => (
                  <AttemptRow key={item.id} item={item} />
                ))}
              </ol>
              {more.error ? <p role="alert">{more.error}</p> : null}
              {more.next !== null ? (
                <button
                  type="button"
                  disabled={more.loading}
                  onClick={loadMore}
                >
                  {more.loading ? "正在读取…" : "显示更早的请求"}
                </button>
              ) : null}
            </>
          )}
          <button type="button" onClick={reload}>
            刷新用量
          </button>
          {state.page.totals.attempts > 0 ? (
            <button type="button" disabled={exporting.busy} onClick={exportCsv}>
              {exporting.busy ? "正在导出…" : "导出 CSV"}
            </button>
          ) : null}
          {exporting.error ? <p role="alert">{exporting.error}</p> : null}
        </>
      ) : null}
    </details>
  );
}
