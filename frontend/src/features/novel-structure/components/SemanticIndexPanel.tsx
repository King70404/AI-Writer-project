import { useCallback, useEffect, useRef, useState } from "react";
import { REASON_LABELS } from "../../usage/api/budget";
import { aiWorkflowClient, type ModelProfile } from "../api/ai-workflow";
import {
  semanticError,
  semanticIndexClient,
  type SemanticIndexClient,
  type SemanticIndexStatus,
} from "../api/semantic-index";

const PROBLEM_TEXT = {
  not_configured: "尚未选择嵌入模型。",
  not_found: "所选嵌入模型配置已不存在，请重新选择。",
  not_embedding: "所选模型不是“嵌入（语义索引）”用途，请重新选择。",
} as const;

/**
 * C-4 语义索引（本书）。展开后才读取状态；读取、预估和保存设置都不调用模型。
 * 建立/增量更新只在作者勾选确认预估后发送，每个请求计入用量并受预算约束。
 */
export function SemanticIndexPanel({
  projectId,
  client = semanticIndexClient,
  loadModels = aiWorkflowClient.models,
}: {
  readonly projectId: string;
  readonly client?: SemanticIndexClient;
  readonly loadModels?: () => Promise<readonly ModelProfile[]>;
}) {
  const [opened, setOpened] = useState(false);
  return (
    <details
      className="semantic-index"
      onToggle={(event) => {
        if (event.currentTarget.open) setOpened(true);
      }}
    >
      <summary>语义索引（可选，建立索引会计费）</summary>
      {opened ? (
        <SemanticIndexBody
          projectId={projectId}
          client={client}
          loadModels={loadModels}
        />
      ) : null}
    </details>
  );
}

function SemanticIndexBody({
  projectId,
  client,
  loadModels,
}: {
  readonly projectId: string;
  readonly client: SemanticIndexClient;
  readonly loadModels: () => Promise<readonly ModelProfile[]>;
}) {
  const [status, setStatus] = useState<SemanticIndexStatus | null>(null);
  const [models, setModels] = useState<readonly ModelProfile[]>([]);
  const [profileId, setProfileId] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [cloudConsent, setCloudConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const lock = useRef(false);
  const apply = useCallback((next: SemanticIndexStatus) => {
    setStatus(next);
    setProfileId(next.settings.profile_id ?? "");
    setEnabled(next.settings.enabled);
    setConfirmed(false);
    setCloudConsent(false);
  }, []);
  const load = useCallback(
    () =>
      Promise.all([client.status(projectId), loadModels()]).then(
        ([nextStatus, nextModels]) => {
          setModels(nextModels.filter((item) => item.purpose === "embedding"));
          apply(nextStatus);
        },
      ),
    [apply, client, loadModels, projectId],
  );
  useEffect(() => {
    let alive = true;
    load().catch((failure: unknown) => {
      if (alive) setError(semanticError(failure).message);
    });
    return () => {
      alive = false;
    };
  }, [load]);
  const refresh = () => run(load);
  const run = async (action: () => Promise<void>) => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (failure) {
      setError(semanticError(failure).message);
      // Partial progress of a failed build is kept: show the remaining plan.
      await client
        .status(projectId)
        .then(apply)
        .catch(() => undefined);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  const saveSettings = () =>
    run(async () => {
      if (!status) return;
      await client.saveSettings(projectId, {
        expected_version: status.settings.version,
        enabled,
        profile_id: profileId || null,
      });
      apply(await client.status(projectId));
      setNotice("语义索引设置已保存。保存设置不会调用模型。");
    });
  const build = () =>
    run(async () => {
      if (!status?.plan) return;
      const result = await client.build(projectId, {
        plan_version: status.plan.plan_version,
        confirm_estimate: true,
        cloud_consent: cloudConsent,
      });
      apply(result.status);
      setNotice(
        `已发送 ${result.requests_sent} 个嵌入请求，写入 ${result.items_indexed} 项，清理 ${result.entries_removed} 项过期索引。用量记录为“建立语义索引（嵌入）”。`,
      );
    });
  if (!status)
    return error ? <p role="alert">{error}</p> : <p>正在读取语义索引…</p>;
  const plan = status.plan;
  const estimate = status.estimate;
  const cloud = status.profile?.kind === "cloud";
  const refused = estimate?.decision === "refused";
  const settingsChanged =
    enabled !== status.settings.enabled ||
    (profileId || null) !== status.settings.profile_id;
  return (
    <section aria-label="语义索引">
      <p>
        语义召回使用你在模型设置里配置的嵌入模型：索引只在你确认预估后手动建立或增量更新，每次都会按服务商价格计费，并计入用量与预算；召回时只读取已保存的向量，不调用模型。没有有效索引或索引过期时，召回会回退为文字关联并在“本次依据”中注明。
      </p>
      <label htmlFor="semantic-profile">嵌入模型</label>
      <select
        id="semantic-profile"
        value={profileId}
        disabled={busy}
        onChange={(event) => setProfileId(event.target.value)}
      >
        <option value="">未选择</option>
        {models.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name} · {item.model} ·{" "}
            {item.kind === "cloud" ? "云端" : "本地"}
          </option>
        ))}
      </select>
      {models.length === 0 ? (
        <p>
          还没有嵌入模型。请在“模型配置”中添加用途为“嵌入（语义索引）”的模型并填写单价。
        </p>
      ) : null}
      <label>
        <input
          type="checkbox"
          checked={enabled}
          disabled={busy}
          onChange={(event) => setEnabled(event.target.checked)}
        />
        召回时使用语义召回（作者固定/排除仍优先）
      </label>
      <button
        type="button"
        disabled={busy || !settingsChanged || (enabled && !profileId)}
        onClick={() => void saveSettings()}
      >
        保存语义索引设置
      </button>
      {status.profile_problem ? (
        <p>{PROBLEM_TEXT[status.profile_problem]}</p>
      ) : null}
      <p>
        已建立索引：已确认事实 {status.facts_indexed} / {status.facts_total}
        ，章节正文 {status.chapters_indexed} / {status.chapters_total}
        ；过期索引 {status.stale_entries} 项。
      </p>
      {status.up_to_date ? <p role="status">语义索引已是最新。</p> : null}
      {plan ? (
        <div aria-label="索引更新预估">
          <p>
            本次待更新：事实 {plan.fact_items} 项、正文分块 {plan.chunk_items}{" "}
            项，共 {plan.input_characters} 字符，分 {plan.requests} 个请求
            {plan.obsolete_entries
              ? `；将清理 ${plan.obsolete_entries} 项过期索引`
              : ""}
            {plan.deferred_items
              ? `；另有 ${plan.deferred_items} 项超出单次上限，留待下次更新`
              : ""}
            。
          </p>
          {estimate && plan.requests ? (
            <p>
              预估输入 token 上限 {estimate.input_tokens_upper}（输出 0）；
              {estimate.estimated_cost_upper && estimate.currency
                ? `预估费用上限 ${estimate.estimated_cost_upper} ${estimate.currency}`
                : "嵌入模型尚未填写单价，无法预估费用"}
              。
              {estimate.decision === "allowed"
                ? ""
                : `预算：${estimate.decision === "refused" ? "严格预算将拒绝" : "超出提醒"}（${estimate.reasons
                    .map((reason) => REASON_LABELS[reason])
                    .join("、")}）。`}
            </p>
          ) : null}
          <label>
            <input
              type="checkbox"
              checked={confirmed}
              disabled={busy || refused}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            我已核对以上预估，确认发送并计费
          </label>
          {cloud ? (
            <label>
              <input
                type="checkbox"
                checked={cloudConsent}
                disabled={busy || refused}
                onChange={(event) => setCloudConsent(event.target.checked)}
              />
              同意把上述事实与正文分块发送给云端嵌入服务
            </label>
          ) : null}
          <button
            type="button"
            disabled={busy || refused || !confirmed || (cloud && !cloudConsent)}
            onClick={() => void build()}
          >
            {busy ? "正在建立索引…" : "确认并建立/更新索引"}
          </button>
        </div>
      ) : null}
      <button type="button" disabled={busy} onClick={() => void refresh()}>
        重新读取状态与预估
      </button>
      {notice ? <p role="status">{notice}</p> : null}
      {error ? <p role="alert">{error}</p> : null}
    </section>
  );
}
