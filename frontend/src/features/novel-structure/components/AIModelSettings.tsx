import { useEffect, useRef, useState } from "react";
import { AIWritingError } from "../api/ai-writing";
import {
  aiWorkflowClient,
  type AIWorkflowClient,
  type ModelProfile,
} from "../api/ai-workflow";

export function AIModelSettings({
  models,
  onSaved,
  onUpgradeRequired,
  disabled = false,
  open,
  onOpenChange,
  focusRequest = 0,
  client = aiWorkflowClient,
}: {
  readonly models: readonly ModelProfile[];
  readonly onSaved: (saved: ModelProfile) => void;
  readonly onUpgradeRequired?: (failure: AIWritingError) => void;
  readonly disabled?: boolean;
  /** 由写作页控制的原地设置抽屉；未提供时保持原有展开方式。 */
  readonly open?: boolean;
  readonly onOpenChange?: (open: boolean) => void;
  /** 每次递增都会把焦点移到“配置名称”，用于“添加模型”捷径。 */
  readonly focusRequest?: number;
  readonly client?: AIWorkflowClient;
}) {
  const [id, setId] = useState<string | undefined>();
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"local" | "cloud">("local");
  const [url, setUrl] = useState("http://127.0.0.1:1234/v1");
  const [model, setModel] = useState("");
  const [tokens, setTokens] = useState("2048");
  const [key, setKey] = useState("");
  const [clearKey, setClearKey] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const saving = useRef(false);
  const nameField = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (focusRequest > 0) nameField.current?.focus();
  }, [focusRequest]);
  const edit = (profile?: ModelProfile) => {
    setId(profile?.id);
    setName(profile?.name ?? "");
    setKind(profile?.kind ?? "local");
    setUrl(profile?.base_url ?? "http://127.0.0.1:1234/v1");
    setModel(profile?.model ?? "");
    setTokens(String(profile?.max_output_tokens ?? 2048));
    setKey("");
    setClearKey(false);
    setMessage("");
    setError("");
  };
  const save = async () => {
    if (saving.current || disabled) return;
    const outputTokens = Number(tokens);
    if (
      !name.trim() ||
      !model.trim() ||
      !url.trim() ||
      !Number.isSafeInteger(outputTokens) ||
      outputTokens < 1 ||
      outputTokens > 16384
    ) {
      setError("请填写名称、模型、服务地址和 1–16384 的输出上限。");
      return;
    }
    saving.current = true;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const saved = await client.saveModel(
        {
          name: name.trim(),
          kind,
          base_url: url.trim(),
          model: model.trim(),
          max_output_tokens: outputTokens,
          ...(kind === "cloud" && key ? { api_key: key } : {}),
          ...(id && clearKey ? { clear_key: true } : {}),
        },
        id,
      );
      setId(saved.id);
      setKey("");
      setClearKey(false);
      onSaved(saved);
      setMessage(
        saved.kind === "cloud" && !saved.has_key
          ? `配置已保存，已选中“${saved.name}”。还需填写 API Key 才能向云端发送。`
          : `配置已保存，已选中“${saved.name}”。密钥不会回显；尚未检查服务连接。`,
      );
    } catch (failure) {
      if (
        failure instanceof AIWritingError &&
        failure.code === "AI_WORKFLOW_SCHEMA_REQUIRED" &&
        onUpgradeRequired
      ) {
        onUpgradeRequired(failure);
        return;
      }
      setError(
        `模型配置保存未确认：${failure instanceof Error ? failure.message : "请重试。"}`,
      );
    } finally {
      saving.current = false;
      setBusy(false);
    }
  };
  return (
    <details
      className="ai-model-settings"
      {...(open === undefined ? {} : { open })}
      onToggle={(event) => onOpenChange?.(event.currentTarget.open)}
    >
      <summary>模型配置</summary>
      <p>
        支持本机或云端 OpenAI-compatible
        服务。云端密钥仅保存在本机受保护存储中。
      </p>
      <ul>
        {models.map((profile) => (
          <li key={profile.id}>
            {profile.name} · {profile.model} ·{" "}
            {profile.kind === "cloud"
              ? profile.has_key
                ? "已保存密钥"
                : "未保存密钥"
              : "本地"}
            <button
              type="button"
              disabled={busy || disabled}
              onClick={() => edit(profile)}
            >
              编辑 {profile.name}
            </button>
          </li>
        ))}
      </ul>
      <button type="button" disabled={busy || disabled} onClick={() => edit()}>
        添加新模型
      </button>
      <form
        aria-label="模型配置表单"
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <fieldset disabled={busy || disabled}>
          <legend>{id ? "编辑模型" : "添加模型"}</legend>
          <label htmlFor="ai-model-name">配置名称</label>
          <input
            ref={nameField}
            id="ai-model-name"
            autoComplete="off"
            value={name}
            maxLength={100}
            onChange={(event) => setName(event.target.value)}
          />
          <label htmlFor="ai-model-kind">服务位置</label>
          <select
            id="ai-model-kind"
            value={kind}
            onChange={(event) => {
              setKind(event.target.value === "cloud" ? "cloud" : "local");
              setKey("");
              setClearKey(false);
            }}
          >
            <option value="local">本机模型</option>
            <option value="cloud">云端模型（HTTPS）</option>
          </select>
          <label htmlFor="ai-model-url">服务地址</label>
          <input
            id="ai-model-url"
            type="url"
            aria-describedby="ai-model-url-help"
            autoComplete="off"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
          />
          <p id="ai-model-url-help">
            填写服务的基础地址（Base URL）。DeepSeek 可填
            https://api.deepseek.com 或 https://api.deepseek.com/v1。
          </p>
          <label htmlFor="ai-model-id">模型名称</label>
          <input
            id="ai-model-id"
            autoComplete="off"
            value={model}
            onChange={(event) => setModel(event.target.value)}
          />
          <label htmlFor="ai-model-tokens">每次输出 Token 上限</label>
          <input
            id="ai-model-tokens"
            inputMode="numeric"
            value={tokens}
            onChange={(event) => setTokens(event.target.value)}
          />
          {kind === "cloud" ? (
            <>
              <label htmlFor="ai-model-key">API Key（留空保留已有密钥）</label>
              <input
                id="ai-model-key"
                type="password"
                autoComplete="new-password"
                value={key}
                onChange={(event) => {
                  setKey(event.target.value);
                  setClearKey(false);
                }}
              />
              {id ? (
                <label>
                  <input
                    type="checkbox"
                    checked={clearKey}
                    onChange={(event) => {
                      setClearKey(event.target.checked);
                      if (event.target.checked) setKey("");
                    }}
                  />
                  移除已保存密钥
                </label>
              ) : null}
            </>
          ) : null}
          <button type="submit" disabled={busy || disabled}>
            {busy ? "正在保存模型…" : "保存模型配置"}
          </button>
        </fieldset>
      </form>
      {message ? <p role="status">{message}</p> : null}
      {error ? <p role="alert">{error}</p> : null}
    </details>
  );
}
