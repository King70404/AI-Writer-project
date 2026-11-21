import { useEffect, useRef, useState } from "react";
import { AIWritingError } from "../api/ai-writing";
import {
  modelConnectionClient,
  type ConnectionResult,
} from "../api/model-connection";
import {
  aiWorkflowClient,
  type AIWorkflowClient,
  type ModelProfile,
} from "../api/ai-workflow";
import { EmbeddingPriceForm } from "./EmbeddingPriceForm";

export function AIModelSettings({
  models,
  projectId,
  onSaved,
  onUpgradeRequired,
  disabled = false,
  open,
  onOpenChange,
  focusRequest = 0,
  client = aiWorkflowClient,
}: {
  readonly models: readonly ModelProfile[];
  readonly projectId?: string;
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
  const [purpose, setPurpose] = useState<"chat" | "embedding">("chat");
  const [url, setUrl] = useState("http://127.0.0.1:1234/v1");
  const [model, setModel] = useState("");
  const [tokens, setTokens] = useState("2048");
  const [key, setKey] = useState("");
  const [clearKey, setClearKey] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [connection, setConnection] = useState<
    Record<string, ConnectionResult>
  >({});
  const [confirmedId, setConfirmedId] = useState<string | null>(null);
  const check = async (profile: ModelProfile, testMessage = false) => {
    if (saving.current || disabled) return;
    const previous = connection[profile.id];
    if (
      testMessage &&
      (!projectId ||
        confirmedId !== profile.id ||
        previous?.status !== "unsupported")
    )
      return;
    saving.current = true;
    setBusy(true);
    setError("");
    setConnection((current) =>
      Object.fromEntries(
        Object.entries(current).filter(
          ([profileId]) => profileId !== profile.id,
        ),
      ),
    );
    try {
      const result =
        testMessage && projectId
          ? await modelConnectionClient.check(profile.id, {
              confirm_test_message: true,
              configuration_version: previous.configuration_version,
              project_id: projectId,
            })
          : await modelConnectionClient.check(profile.id);
      setConnection((current) => ({ ...current, [profile.id]: result }));
    } catch {
      setError("连接检查未完成，配置仍保留，请重试。");
    } finally {
      saving.current = false;
      setConfirmedId(null);
      setBusy(false);
    }
  };
  const saving = useRef(false);
  const nameField = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (focusRequest > 0) nameField.current?.focus();
  }, [focusRequest]);
  const edit = (profile?: ModelProfile) => {
    setId(profile?.id);
    setName(profile?.name ?? "");
    setKind(profile?.kind ?? "local");
    setPurpose(profile?.purpose ?? "chat");
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
          ...(purpose === "embedding" ? { purpose } : {}),
          ...(kind === "cloud" && key ? { api_key: key } : {}),
          ...(id && clearKey ? { clear_key: true } : {}),
        },
        id,
      );
      setId(saved.id);
      setKey("");
      setClearKey(false);
      onSaved(saved);
      setConnection({});
      setMessage(
        saved.kind === "cloud" && !saved.has_key
          ? `配置已保存${saved.purpose === "embedding" ? "" : `，已选中“${saved.name}”`}。还需填写 API Key 才能向云端发送。`
          : saved.purpose === "embedding"
            ? `嵌入模型“${saved.name}”已保存。可在下方填写嵌入单价，并在“长篇记忆与评审”的语义索引中选用。`
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
            {profile.purpose === "embedding" ? "嵌入（语义索引） · " : ""}
            {profile.kind === "cloud"
              ? profile.has_key
                ? "已保存密钥"
                : "未保存密钥"
              : "本地"}
            <button
              type="button"
              disabled={busy || disabled}
              onClick={() => void check(profile)}
            >
              检查连接 {profile.name}
            </button>
            {connection[profile.id] ? (
              <p role="status">
                {connection[profile.id].status === "verified"
                  ? "连接已验证"
                  : ({
                      missing_key: "未保存密钥",
                      unauthorized: "认证失败（401）",
                      forbidden: "访问被拒绝（403）",
                      timeout: "连接超时",
                      dns_error: "域名解析失败",
                      certificate_error: "证书验证失败",
                      model_not_found: "服务可达，但未找到配置的模型",
                      unsupported: "服务不支持元数据检查，连接尚未验证",
                      invalid_response: "服务响应格式无效",
                      unavailable: "服务暂不可用",
                    }[connection[profile.id].status] ?? "连接尚未验证")}
                {" · 配置版本 "}
                {connection[profile.id].configuration_version.slice(0, 12)}
              </p>
            ) : null}
            {connection[profile.id]?.status === "unsupported" &&
            profile.purpose === "embedding" ? (
              <p>
                嵌入模型不提供测试消息；首次建立语义索引时会在你确认预估费用后实际调用。
              </p>
            ) : null}
            {connection[profile.id]?.status === "unsupported" &&
            profile.purpose !== "embedding" ? (
              <div>
                <p>
                  将发送一条测试消息，可能计费。费用计入当前小说用量并受预算约束；测试结果不会进入正文。
                </p>
                {projectId ? (
                  <>
                    <label>
                      <input
                        type="checkbox"
                        checked={confirmedId === profile.id}
                        disabled={busy || disabled}
                        onChange={(event) =>
                          setConfirmedId(
                            event.target.checked ? profile.id : null,
                          )
                        }
                      />
                      我同意发送可能计费的测试消息
                    </label>
                    <button
                      type="button"
                      disabled={busy || disabled || confirmedId !== profile.id}
                      onClick={() => void check(profile, true)}
                    >
                      确认发送测试消息 {profile.name}
                    </button>
                  </>
                ) : (
                  <p>请从小说写作页打开模型设置，以便归属用量与预算。</p>
                )}
              </div>
            ) : null}
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
          <label htmlFor="ai-model-purpose">用途</label>
          <select
            id="ai-model-purpose"
            value={purpose}
            onChange={(event) =>
              setPurpose(
                event.target.value === "embedding" ? "embedding" : "chat",
              )
            }
          >
            <option value="chat">生成与评审</option>
            <option value="embedding">嵌入（语义索引）</option>
          </select>
          {purpose === "embedding" ? (
            <p>
              嵌入模型只在你确认预估费用后用于建立语义索引，每次建立/更新索引都会按服务商价格计费，并计入用量与预算；不会用于生成正文。
            </p>
          ) : null}
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
          {purpose === "chat" ? (
            <>
              <label htmlFor="ai-model-tokens">每次输出 Token 上限</label>
              <input
                id="ai-model-tokens"
                inputMode="numeric"
                value={tokens}
                onChange={(event) => setTokens(event.target.value)}
              />
            </>
          ) : null}
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
      {id && purpose === "embedding" ? (
        <EmbeddingPriceForm
          key={id}
          profileId={id}
          profileName={models.find((item) => item.id === id)?.name ?? name}
        />
      ) : null}
      {message ? <p role="status">{message}</p> : null}
      {error ? <p role="alert">{error}</p> : null}
    </details>
  );
}
