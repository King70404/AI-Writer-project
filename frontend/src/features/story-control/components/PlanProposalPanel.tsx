import { useCallback, useEffect, useState } from "react";

import { OperationSendGuard } from "../../usage/components/SendEstimatePanel";
import {
  planProposalClient,
  planProposalError,
  type PlanProposal,
  type PlanProposalClient,
  type ProposalCard,
  type ProposalModel,
} from "../api/planProposal";
import type { ArcPlan, Goal } from "../api/storyControl";

function chapterLabel(plan: ArcPlan, chapterId: string): string {
  const chapter = plan.chapters.find((item) => item.chapter_id === chapterId);
  return chapter
    ? `第${chapter.volume_position}卷第${chapter.position}章「${chapter.title}」`
    : "章节已不存在";
}

function volumeLabel(plan: ArcPlan, volumeId: string | null): string {
  if (volumeId === null) return "全书";
  const volume = plan.volumes.find((item) => item.volume_id === volumeId);
  return volume ? `第${volume.position}卷「${volume.title}」` : "分卷已不存在";
}

function CardBody({
  plan,
  card,
}: {
  readonly plan: ArcPlan;
  readonly card: ProposalCard;
}) {
  if (card.kind === "chapter_link")
    return (
      <span>
        挂接章节：{chapterLabel(plan, card.chapter_id)}
        {card.note ? `——${card.note}` : ""}
        {card.reason ? `（理由：${card.reason}）` : ""}
      </span>
    );
  const parts = [
    card.conflict && `冲突：${card.conflict}`,
    card.obstacle && `阻碍：${card.obstacle}`,
    card.turn && `转折：${card.turn}`,
    card.outcome && `变化：${card.outcome}`,
  ].filter(Boolean);
  return (
    <span>
      新子目标「{card.title}」（{volumeLabel(plan, card.volume_id)}）
      {parts.length ? `：${parts.join("；")}` : ""}
      {card.chapter_ids.length
        ? ` · 落实章节：${card.chapter_ids.map((item) => chapterLabel(plan, item)).join("、")}`
        : ""}
      {card.reason ? `（理由：${card.reason}）` : ""}
    </span>
  );
}

/**
 * 选定目标的“建议拆分”。准备与预估不调用模型；作者确认后只发送一次。
 * 建议卡只有被勾选并点击“采用所选”后才写入规划，且不会创建或修改章节。
 */
export function PlanProposalPanel({
  projectId,
  goal,
  plan,
  onAdopted,
  onClose,
  client = planProposalClient,
}: {
  readonly projectId: string;
  readonly goal: Goal;
  readonly plan: ArcPlan;
  readonly onAdopted: () => void;
  readonly onClose: () => void;
  readonly client?: PlanProposalClient;
}) {
  const [models, setModels] = useState<readonly ProposalModel[]>([]);
  const [profileId, setProfileId] = useState("");
  const [authorRequest, setAuthorRequest] = useState("");
  const [proposal, setProposal] = useState<PlanProposal | null>(null);
  const [selected, setSelected] = useState<readonly number[]>([]);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);

  useEffect(() => {
    let alive = true;
    Promise.all([client.models(), client.list(projectId)])
      .then(([profiles, proposals]) => {
        if (!alive) return;
        setModels(profiles);
        setProfileId((current) => current || (profiles[0]?.id ?? ""));
        const latest = proposals.find(
          (item) => item.goal_id === goal.id && item.status !== "failed",
        );
        if (latest) setProposal(latest);
      })
      .catch((reason: unknown) => {
        if (alive) setError(planProposalError(reason).message);
      });
    return () => {
      alive = false;
    };
  }, [client, goal.id, projectId]);

  const act = async (label: string, action: () => Promise<void>) => {
    setBusy(label);
    setError("");
    try {
      await action();
    } catch (reason) {
      const failure = planProposalError(reason);
      setError(failure.message);
      if (failure.code === "PLAN_PROPOSAL_STALE") setStale(true);
    } finally {
      setBusy("");
    }
  };

  const prepare = () =>
    act("正在冻结规划快照（不调用模型）…", async () => {
      const next = await client.prepare(
        projectId,
        goal.id,
        profileId,
        authorRequest.trim(),
      );
      setProposal(next);
      setSelected([]);
      setConsent(false);
      setStale(false);
    });

  const loadEstimate = useCallback(
    () =>
      proposal
        ? client.estimate(projectId, proposal.id)
        : Promise.reject(new Error("no proposal")),
    [client, projectId, proposal],
  );

  const send = () =>
    act("正在发送一次并等待建议卡…", async () => {
      if (!proposal) return;
      const next = await client.send(projectId, proposal, consent);
      setProposal(next);
    });

  const adopt = () =>
    act("正在采用所选建议卡…", async () => {
      if (!proposal) return;
      const next = await client.adopt(projectId, proposal.id, selected);
      setProposal(next);
      setSelected([]);
      onAdopted();
    });

  const reset = () => {
    setProposal(null);
    setSelected([]);
    setStale(false);
    setError("");
  };

  const children = plan.goals.filter((view) =>
    view.goal.parent_goal_ids.includes(goal.id),
  );
  const adopted = new Set(proposal?.adoptions.map((item) => item.index));

  return (
    <section
      className="story-control__proposal"
      aria-label={`「${goal.title}」的建议拆分`}
    >
      <h5>建议拆分：「{goal.title}」</h5>
      {error ? <p role="alert">{error}</p> : null}
      {busy ? <p role="status">{busy}</p> : null}

      {proposal === null ? (
        <div>
          <p>
            将冻结下列已保存规划和章节标题（不含正文），由你确认预估后发送一次给模型，生成建议卡。
            建议卡需要你逐张勾选采用，才会写入规划；不会创建或修改章节。
          </p>
          <ul>
            <li>
              当前目标：{goal.scope === "book" ? "全书" : "分卷"}「{goal.title}
              」{goal.conflict ? `，核心冲突：${goal.conflict}` : ""}
            </li>
            <li>
              已关联章节：
              {goal.links.length
                ? goal.links
                    .map((link) => chapterLabel(plan, link.chapter_id))
                    .join("、")
                : "无"}
            </li>
            <li>
              已有子目标：
              {children.length
                ? children.map((view) => `「${view.goal.title}」`).join("、")
                : "无"}
            </li>
          </ul>
          <label className="story-control__field">
            <span>拆分要求（可选，最多 500 字）</span>
            <textarea
              maxLength={500}
              value={authorRequest}
              onChange={(event) => setAuthorRequest(event.target.value)}
            />
          </label>
          <label className="story-control__field">
            <span>模型</span>
            <select
              value={profileId}
              onChange={(event) => setProfileId(event.target.value)}
            >
              {models.length === 0 ? (
                <option value="">请先在 AI 设置中添加模型</option>
              ) : null}
              {models.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.name}（{model.kind === "cloud" ? "云端" : "本机"}）
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={!profileId || Boolean(busy)}
            onClick={() => void prepare()}
          >
            准备建议（冻结快照，不调用模型）
          </button>
        </div>
      ) : null}

      {proposal?.status === "ready" ? (
        <div>
          <p>
            已冻结：目标「{proposal.source.title}」第 {proposal.source.version}{" "}
            版、{proposal.children.length} 个已有子目标、
            {proposal.chapters.length} 个章节标题
            {proposal.chapters_omitted
              ? `（另有 ${proposal.chapters_omitted} 章超出上限未发送）`
              : ""}
            。模型：{proposal.model_name}。
          </p>
          <details>
            <summary>查看将发送的完整内容</summary>
            <pre className="story-control__preview">
              {proposal.request_preview}
            </pre>
          </details>
          <OperationSendGuard
            loadEstimate={loadEstimate}
            refreshKey={`${proposal.id}:${proposal.version}`}
          >
            {(allowed) => (
              <div>
                {proposal.model_kind === "cloud" ? (
                  <label>
                    <input
                      type="checkbox"
                      checked={consent}
                      onChange={(event) => setConsent(event.target.checked)}
                    />
                    同意把上述冻结内容发送给云端模型
                  </label>
                ) : null}
                <button
                  type="button"
                  disabled={
                    !allowed ||
                    Boolean(busy) ||
                    (proposal.model_kind === "cloud" && !consent)
                  }
                  onClick={() => void send()}
                >
                  发送一次，生成建议卡
                </button>
              </div>
            )}
          </OperationSendGuard>
          <button type="button" onClick={reset}>
            放弃本次准备
          </button>
        </div>
      ) : null}

      {proposal?.status === "running" ? (
        <p role="status">该建议正在生成中或曾被中断，请稍后刷新查看结果。</p>
      ) : null}

      {proposal?.status === "failed" ? (
        <div role="alert">
          <p>
            {proposal.error === "PlanProposalOutputInvalid"
              ? "模型回复不是有效的建议格式，未生成建议卡，规划未改变。原始回复已保留，系统不会自动重试。"
              : "本次建议生成失败，规划未改变；系统不会自动重试。"}
          </p>
          {proposal.evidence !== null ? (
            <details>
              <summary>
                查看原始回复{proposal.evidence_truncated ? "（已截断）" : ""}
              </summary>
              <pre className="story-control__preview">{proposal.evidence}</pre>
            </details>
          ) : null}
          <button type="button" onClick={reset}>
            重新准备
          </button>
        </div>
      ) : null}

      {proposal?.status === "completed" ? (
        <div>
          {proposal.summary ? <p>模型思路：{proposal.summary}</p> : null}
          {proposal.cards.length === 0 ? (
            <p>模型没有给出建议卡；规划未改变。</p>
          ) : (
            <ul className="story-control__list">
              {proposal.cards.map((card, index) => (
                <li key={index}>
                  <label>
                    <input
                      type="checkbox"
                      aria-label={`选择建议卡 ${index + 1}`}
                      disabled={adopted.has(index) || Boolean(busy)}
                      checked={adopted.has(index) || selected.includes(index)}
                      onChange={() =>
                        setSelected((current) =>
                          current.includes(index)
                            ? current.filter((item) => item !== index)
                            : [...current, index],
                        )
                      }
                    />
                    <CardBody plan={plan} card={card} />
                    {adopted.has(index) ? " · 已采用" : ""}
                  </label>
                </li>
              ))}
            </ul>
          )}
          {stale ? (
            <button type="button" onClick={reset}>
              重新准备建议
            </button>
          ) : (
            <button
              type="button"
              disabled={selected.length === 0 || Boolean(busy)}
              onClick={() => void adopt()}
            >
              采用所选（{selected.length}）
            </button>
          )}
          <button type="button" onClick={reset}>
            另起一次建议
          </button>
        </div>
      ) : null}
      <button type="button" onClick={onClose}>
        关闭建议拆分
      </button>
    </section>
  );
}
