import { useEffect, useState, type FormEvent } from "react";
import {
  budgetClient as defaultBudgetClient,
  BudgetError,
  isAmount,
  isCurrency,
  type BudgetClient,
  type PriceState,
} from "../../usage/api/budget";

/**
 * C-4：嵌入模型单价（每百万输入 token）。嵌入没有输出 token，输出单价固定保存为 0。
 * 价格按版本追加；读取与保存都不调用模型。
 */
export function EmbeddingPriceForm({
  profileId,
  profileName,
  client = defaultBudgetClient,
}: {
  readonly profileId: string;
  readonly profileName: string;
  readonly client?: BudgetClient;
}) {
  const [state, setState] = useState<PriceState | null>(null);
  const [currency, setCurrency] = useState("");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    let alive = true;
    client
      .price(profileId)
      .then((value) => {
        if (alive) setState(value);
      })
      .catch((failure: unknown) => {
        if (alive)
          setError(
            failure instanceof BudgetError ? failure.message : "价格读取失败。",
          );
      });
    return () => {
      alive = false;
    };
  }, [client, profileId]);
  const current = state?.current ?? null;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const code = (currency || current?.currency || "").trim().toUpperCase();
    const price = input || current?.input_per_million || "";
    if (!isCurrency(code) || !isAmount(price)) {
      setError("请填写 3 位大写币种（如 CNY）和不超过 6 位小数的非负单价。");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const saved = await client.savePrice(profileId, {
        expected_version: current?.version ?? 0,
        currency: code,
        input_per_million: price,
        output_per_million: "0",
      });
      setState(saved);
      setCurrency("");
      setInput("");
      setNotice("嵌入单价已保存为新版本；之前的请求仍按当时的价格计算。");
    } catch (failure) {
      setError(
        failure instanceof BudgetError ? failure.message : "价格保存未确认。",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <form aria-label="嵌入模型单价" onSubmit={(event) => void submit(event)}>
      <h4>嵌入单价 · {profileName}</h4>
      <p>
        {current
          ? `当前单价：每百万输入 token ${current.input_per_million} ${current.currency}（第 ${current.version} 版）。`
          : state
            ? "单价未填写。本应用不预置价格；未填单价时，严格预算会拒绝建立索引。"
            : "正在读取单价…"}
      </p>
      <label htmlFor="embedding-price-currency">币种（如 CNY、USD）</label>
      <input
        id="embedding-price-currency"
        value={currency}
        placeholder={current?.currency ?? "CNY"}
        maxLength={3}
        onChange={(event) => setCurrency(event.target.value)}
      />
      <label htmlFor="embedding-price-input">输入单价（每百万 token）</label>
      <input
        id="embedding-price-input"
        inputMode="decimal"
        value={input}
        placeholder={current?.input_per_million ?? ""}
        onChange={(event) => setInput(event.target.value)}
      />
      <button type="submit" disabled={busy}>
        {busy ? "正在保存单价…" : "保存嵌入单价"}
      </button>
      {error ? <p role="alert">{error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
    </form>
  );
}
