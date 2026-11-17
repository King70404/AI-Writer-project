import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  budgetClient as defaultBudgetClient,
  BudgetError,
  isAmount,
  isCurrency,
  MODE_LABELS,
  type BudgetClient,
  type BudgetMode,
  type BudgetView,
  type PriceState,
} from "../api/budget";

function message(error: unknown): string {
  return error instanceof BudgetError
    ? error.message
    : "操作未完成，请稍后重试；写作不受影响。";
}

/**
 * 费用与预算（B2）：作者为当前模型填写价格、为本书设置预算。
 * 不预置价格，不换汇；读取与保存都不调用模型。展开后才读取。
 */
export function BudgetSettingsPanel({
  projectId,
  profileId,
  profileName,
  initiallyOpen = false,
  client = defaultBudgetClient,
}: {
  readonly projectId: string;
  readonly profileId: string | null;
  readonly profileName: string;
  readonly initiallyOpen?: boolean;
  readonly client?: BudgetClient;
}) {
  const [opened, setOpened] = useState(false);
  return (
    <details
      open={initiallyOpen || undefined}
      className="budget-settings"
      onToggle={(event) => {
        if (event.currentTarget.open) setOpened(true);
      }}
    >
      <summary>费用与预算</summary>
      {opened || initiallyOpen ? (
        <>
          {profileId ? (
            <PriceForm
              key={profileId}
              profileId={profileId}
              profileName={profileName}
              client={client}
            />
          ) : (
            <p>添加并选择模型后可填写价格。</p>
          )}
          <BudgetForm projectId={projectId} client={client} />
        </>
      ) : null}
    </details>
  );
}

function useLoad<T>(load: () => Promise<T>) {
  const [value, setValue] = useState<T | null>(null);
  const [error, setError] = useState("");
  const loader = useRef(load);
  useEffect(() => {
    let alive = true;
    loader
      .current()
      .then((result) => {
        if (alive) setValue(result);
      })
      .catch((failure: unknown) => {
        if (alive) setError(message(failure));
      });
    return () => {
      alive = false;
    };
  }, []);
  return { value, setValue, error, setError };
}

function PriceForm({
  profileId,
  profileName,
  client,
}: {
  readonly profileId: string;
  readonly profileName: string;
  readonly client: BudgetClient;
}) {
  const state = useLoad<PriceState>(() => client.price(profileId));
  const [currency, setCurrency] = useState("");
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const current = state.value?.current ?? null;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const code = (currency || current?.currency || "").trim().toUpperCase();
    const inputPrice = input || current?.input_per_million || "";
    const outputPrice = output || current?.output_per_million || "";
    if (!isCurrency(code) || !isAmount(inputPrice) || !isAmount(outputPrice)) {
      state.setError(
        "请填写 3 位大写币种（如 CNY）和不超过 6 位小数的非负价格。",
      );
      return;
    }
    setSaving(true);
    state.setError("");
    setNotice("");
    try {
      const saved = await client.savePrice(profileId, {
        expected_version: current?.version ?? 0,
        currency: code,
        input_per_million: inputPrice,
        output_per_million: outputPrice,
      });
      state.setValue(saved);
      setCurrency("");
      setInput("");
      setOutput("");
      setNotice("价格已保存为新版本；之前的请求仍按当时的价格计算。");
    } catch (failure) {
      state.setError(message(failure));
    } finally {
      setSaving(false);
    }
  };
  return (
    <form aria-label="模型价格" onSubmit={(event) => void submit(event)}>
      <h4>模型价格 · {profileName}</h4>
      <p>
        {current
          ? `当前价格：每百万 token 输入 ${current.input_per_million} / 输出 ${current.output_per_million} ${current.currency}（第 ${current.version} 版）。`
          : state.value
            ? "价格未填写。本应用不预置价格；请按服务商价目自行填写，本地模型可填 0。"
            : "正在读取价格…"}
      </p>
      {state.error ? <p role="alert">{state.error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      <label htmlFor="price-currency">币种（如 CNY、USD）</label>
      <input
        id="price-currency"
        value={currency}
        placeholder={current?.currency ?? "CNY"}
        maxLength={3}
        onChange={(event) => setCurrency(event.target.value)}
      />
      <label htmlFor="price-input">输入价格（每百万 token）</label>
      <input
        id="price-input"
        inputMode="decimal"
        value={input}
        placeholder={current?.input_per_million ?? ""}
        onChange={(event) => setInput(event.target.value)}
      />
      <label htmlFor="price-output">输出价格（每百万 token）</label>
      <input
        id="price-output"
        inputMode="decimal"
        value={output}
        placeholder={current?.output_per_million ?? ""}
        onChange={(event) => setOutput(event.target.value)}
      />
      <button type="submit" disabled={saving || !state.value}>
        {saving ? "正在保存价格…" : "保存价格"}
      </button>
    </form>
  );
}

function BudgetForm({
  projectId,
  client,
}: {
  readonly projectId: string;
  readonly client: BudgetClient;
}) {
  const state = useLoad<BudgetView>(() => client.budget(projectId));
  const [edits, setEdits] = useState<{
    mode?: BudgetMode;
    currency?: string;
    task?: string;
    monthly?: string;
  }>({});
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const budget = state.value;
  const mode = edits.mode ?? budget?.mode ?? "off";
  const currency = edits.currency ?? budget?.currency ?? "";
  const task = edits.task ?? budget?.task_limit ?? "";
  const monthly = edits.monthly ?? budget?.monthly_limit ?? "";
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!budget) return;
    const code = currency.trim().toUpperCase();
    const enabled = mode !== "off";
    if (
      enabled &&
      (!isCurrency(code) ||
        (!task && !monthly) ||
        (task !== "" && !isAmount(task)) ||
        (monthly !== "" && !isAmount(monthly)))
    ) {
      state.setError(
        "启用预算需要 3 位大写币种和至少一项上限；金额为不超过 6 位小数的非负数。",
      );
      return;
    }
    setSaving(true);
    state.setError("");
    setNotice("");
    try {
      const saved = await client.saveBudget(projectId, {
        expected_version: budget.version,
        mode,
        currency: enabled ? code : null,
        task_limit: enabled && task ? task : null,
        monthly_limit: enabled && monthly ? monthly : null,
      });
      state.setValue(saved);
      setEdits({});
      setNotice("预算已保存为新版本。");
    } catch (failure) {
      state.setError(message(failure));
    } finally {
      setSaving(false);
    }
  };
  const month = budget?.month;
  return (
    <form aria-label="本书预算" onSubmit={(event) => void submit(event)}>
      <h4>本书预算</h4>
      {budget && month ? (
        <p>
          本月（自 {new Date(budget.month_start).toLocaleDateString("zh-CN")}
          起）已发出 {month.attempts} 次请求
          {month.currency
            ? `：按服务商报告计 ${month.settled} ${month.currency}，用量未知按保守预留计 ${month.pending} ${month.currency}，合计上限 ${month.upper} ${month.currency}`
            : ""}
          {month.unpriced_attempts
            ? `；${month.unpriced_attempts} 次发生在填写价格前，金额未知，未按 0 计`
            : ""}
          {month.other_currency_attempts
            ? `；${month.other_currency_attempts} 次使用其他币种价格，未换汇相加`
            : ""}
          。
        </p>
      ) : (
        <p>{state.error ? "" : "正在读取预算…"}</p>
      )}
      {state.error ? <p role="alert">{state.error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      <label htmlFor="budget-mode">预算方式</label>
      <select
        id="budget-mode"
        value={mode}
        onChange={(event) =>
          setEdits((value) => ({
            ...value,
            mode: event.target.value as BudgetMode,
          }))
        }
      >
        {(Object.keys(MODE_LABELS) as BudgetMode[]).map((item) => (
          <option key={item} value={item}>
            {MODE_LABELS[item]}
          </option>
        ))}
      </select>
      {mode === "off" ? null : (
        <>
          <label htmlFor="budget-currency">预算币种</label>
          <input
            id="budget-currency"
            value={currency}
            maxLength={3}
            onChange={(event) =>
              setEdits((value) => ({ ...value, currency: event.target.value }))
            }
          />
          <label htmlFor="budget-task">单任务上限（可空）</label>
          <input
            id="budget-task"
            inputMode="decimal"
            value={task}
            onChange={(event) =>
              setEdits((value) => ({ ...value, task: event.target.value }))
            }
          />
          <label htmlFor="budget-monthly">本书每月上限（可空）</label>
          <input
            id="budget-monthly"
            inputMode="decimal"
            value={monthly}
            onChange={(event) =>
              setEdits((value) => ({ ...value, monthly: event.target.value }))
            }
          />
          <p>
            严格模式需要当前模型已填写同币种价格；价格未填写、币种不同或存在未计价的请求时会拒绝发送。
            用量未知的请求按发送前的保守预留计入，不按 0 计。
          </p>
        </>
      )}
      <button type="submit" disabled={saving || !budget}>
        {saving ? "正在保存预算…" : "保存预算"}
      </button>
    </form>
  );
}
