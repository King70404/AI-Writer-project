import { useCallback, useEffect, useState } from "react";

import { OperationSendGuard } from "../../usage/components/SendEstimatePanel";
import {
  timelineExtractionClient,
  timelineExtractionError,
  type ExtractionModel,
  type RangeProblem,
  type TimelineCard,
  type TimelineCardCheck,
  type TimelineCardProblem,
  type TimelineExtraction,
  type TimelineExtractionClient,
  type TimelineRangePreview,
} from "../api/timelineExtraction";
import { ATTRIBUTE_LABELS, type ArcPlan } from "../api/storyControl";

const MAX_CHAPTERS = 10;

const RANGE_PROBLEMS: Record<RangeProblem, string> = {
  too_many_chapters: "所选章节超过上限，请减少章节。",
  too_many_characters: "所选章节正文合计超过字数上限，请缩小范围。",
  empty_chapter: "所选范围里有尚无正文的章节，请去掉它。",
};

const CARD_PROBLEMS: Record<TimelineCardProblem, string> = {
  quote_not_found: "引文在冻结的原文中找不到，不能采用",
  unknown_chapter: "引用了不在所选范围内的章节，不能采用",
  unknown_character: "引用了不存在或未冻结的人物，不能采用",
  unknown_event: "引用了不存在或未冻结的事件，不能采用",
  unknown_state: "要结束的人物状态不存在或已结束，不能采用",
  unknown_event_card: "开始事件指向的建议事件卡无效，不能采用",
  duplicate_title: "与已有事件或前一张卡同名，不能采用",
  duplicate_end: "与另一张卡重复结束同一人物状态，不能采用",
  state_mismatch: "要结束的状态属于另一个人物，不能采用",
};

function chapterLabel(plan: ArcPlan, chapterId: string): string {
  const chapter = plan.chapters.find((item) => item.chapter_id === chapterId);
  return chapter
    ? `第${chapter.volume_position}卷第${chapter.position}章「${chapter.title}」`
    : "章节已不存在";
}

function CardBody({
  plan,
  extraction,
  card,
  check,
}: {
  readonly plan: ArcPlan;
  readonly extraction: TimelineExtraction;
  readonly card: TimelineCard;
  readonly check: TimelineCardCheck;
}) {
  const where = chapterLabel(plan, card.chapter_id);
  const name = (characterId: string) =>
    extraction.characters.find((item) => item.character_id === characterId)
      ?.name ?? "未知人物";
  const eventTitle = (eventId: string) =>
    extraction.events.find((item) => item.id === eventId)?.title ?? "未知事件";
  let head: string;
  if (card.kind === "event") {
    const people = card.character_ids.map(name).join("、");
    head = `事件「${card.title}」发生于${where}${
      card.story_time ? `（故事时间：${card.story_time}）` : ""
    }${card.description ? `：${card.description}` : ""}${
      people ? ` · 人物：${people}` : ""
    }${
      card.after_event_ids.length
        ? ` · 在「${card.after_event_ids.map(eventTitle).join("」「")}」之后`
        : ""
    }`;
  } else {
    const startCard =
      card.start_event_card === null
        ? null
        : extraction.cards[card.start_event_card];
    const start =
      card.start_event_id !== null
        ? `已有事件「${eventTitle(card.start_event_id)}」`
        : startCard?.kind === "event"
          ? `建议事件卡 ${(card.start_event_card ?? 0) + 1}「${startCard.title}」`
          : "无效的事件卡";
    const ended = extraction.states.find(
      (item) => item.id === card.ends_state_id,
    );
    head = `${name(card.character_id)} · ${ATTRIBUTE_LABELS[card.attribute]}「${
      card.label
    }」：${card.value}（从${start}开始，证据在${where}）${
      card.ends_state_id
        ? ` · 结束原状态「${ended ? `${ended.label}：${ended.value}` : "未知状态"}」`
        : ""
    }`;
  }
  return (
    <span>
      {head}
      <q>{card.quote}</q>
      {card.reason ? `（理由：${card.reason}）` : ""}
      {check.valid ? null : (
        <strong> · {CARD_PROBLEMS[check.problem ?? "quote_not_found"]}</strong>
      )}
    </span>
  );
}

/**
 * 批量提取故事事件与人物状态。选择范围、预览、准备与预估都不调用模型；作者确认后整段只发送一次。
 * 引文或引用未通过核对的卡不能勾选；勾选并点击“采用所选”后才写入事件和人物状态。
 * 勾选一张从建议事件开始的人物状态卡时，会一并勾选那张事件卡。
 */
export function TimelineExtractionPanel({
  projectId,
  plan,
  onAdopted,
  onClose,
  client = timelineExtractionClient,
}: {
  readonly projectId: string;
  readonly plan: ArcPlan;
  readonly onAdopted: () => void;
  readonly onClose: () => void;
  readonly client?: TimelineExtractionClient;
}) {
  const [models, setModels] = useState<readonly ExtractionModel[]>([]);
  const [profileId, setProfileId] = useState("");
  const [authorRequest, setAuthorRequest] = useState("");
  const [range, setRange] = useState<readonly string[]>([]);
  const [preview, setPreview] = useState<TimelineRangePreview | null>(null);
  const [extraction, setExtraction] = useState<TimelineExtraction | null>(null);
  const [selected, setSelected] = useState<readonly number[]>([]);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);

  useEffect(() => {
    let alive = true;
    Promise.all([client.models(), client.list(projectId)])
      .then(async ([profiles, items]) => {
        if (!alive) return;
        setModels(profiles);
        setProfileId((current) => current || (profiles[0]?.id ?? ""));
        const latest = items.find((item) => item.status !== "failed");
        if (latest) {
          const loaded = await client.get(projectId, latest.id);
          if (alive) setExtraction(loaded);
        }
      })
      .catch((reason: unknown) => {
        if (alive) setError(timelineExtractionError(reason).message);
      });
    return () => {
      alive = false;
    };
  }, [client, projectId]);

  const act = async (label: string, action: () => Promise<void>) => {
    setBusy(label);
    setError("");
    try {
      await action();
    } catch (reason) {
      const failure = timelineExtractionError(reason);
      setError(failure.message);
      if (failure.code === "TIMELINE_EXTRACTION_STALE") setStale(true);
    } finally {
      setBusy("");
    }
  };

  const toggleChapter = (chapterId: string) => {
    setPreview(null);
    setRange((current) =>
      current.includes(chapterId)
        ? current.filter((item) => item !== chapterId)
        : [...current, chapterId],
    );
  };

  const loadPreview = () =>
    act("正在统计所选章节（不调用模型）…", async () => {
      setPreview(await client.preview(projectId, range));
    });

  const prepare = () =>
    act("正在冻结所选章节正文（不调用模型）…", async () => {
      const next = await client.prepare(
        projectId,
        range,
        profileId,
        authorRequest.trim(),
      );
      setExtraction(next);
      setSelected([]);
      setConsent(false);
      setStale(false);
    });

  const loadEstimate = useCallback(
    () =>
      extraction
        ? client.estimate(projectId, extraction.id)
        : Promise.reject(new Error("no extraction")),
    [client, projectId, extraction],
  );

  const send = () =>
    act("正在发送一次并等待建议卡…", async () => {
      if (!extraction) return;
      setExtraction(await client.send(projectId, extraction, consent));
    });

  const adopt = () =>
    act("正在采用所选建议卡…", async () => {
      if (!extraction) return;
      const next = await client.adopt(projectId, extraction.id, selected);
      setExtraction(next);
      setSelected([]);
      onAdopted();
    });

  const reset = () => {
    setExtraction(null);
    setPreview(null);
    setSelected([]);
    setStale(false);
    setError("");
  };

  const adopted = new Set(extraction?.adoptions.map((item) => item.index));

  const toggleCard = (index: number) => {
    if (!extraction) return;
    const dependsOn = (other: number) => {
      const item = extraction.cards[other];
      return item.kind === "state" && item.start_event_card === index;
    };
    setSelected((current) => {
      if (current.includes(index))
        // Unselecting an event also unselects the states that start at it.
        return current.filter((item) => item !== index && !dependsOn(item));
      const card = extraction.cards[index];
      const start = card.kind === "state" ? card.start_event_card : null;
      return start !== null && !adopted.has(start) && !current.includes(start)
        ? [...current, start, index]
        : [...current, index];
    });
  };

  return (
    <section
      className="story-control__proposal"
      aria-label="批量提取事件与人物状态"
    >
      <h5>批量提取事件与人物状态</h5>
      {error ? <p role="alert">{error}</p> : null}
      {busy ? <p role="status">{busy}</p> : null}

      {extraction === null ? (
        <div>
          <p>
            选择最多 {MAX_CHAPTERS}{" "}
            章已保存正文，由你确认预估后整段发送一次给模型，生成故事事件和人物状态的证据卡。
            每张卡的引文都会在原文中逐字核对；只有你勾选采用的有效卡才会写入时间线和人物状态，正文不会被修改。
          </p>
          <fieldset>
            <legend>选择章节（已选 {range.length}）</legend>
            {plan.chapters.map((item) => (
              <label key={item.chapter_id}>
                <input
                  type="checkbox"
                  checked={range.includes(item.chapter_id)}
                  disabled={
                    Boolean(busy) ||
                    (!range.includes(item.chapter_id) &&
                      range.length >= MAX_CHAPTERS)
                  }
                  onChange={() => toggleChapter(item.chapter_id)}
                />
                {chapterLabel(plan, item.chapter_id)}
              </label>
            ))}
          </fieldset>
          <button
            type="button"
            disabled={range.length === 0 || Boolean(busy)}
            onClick={() => void loadPreview()}
          >
            预览所选范围（不调用模型）
          </button>
          {preview ? (
            <div>
              <ul>
                {preview.chapters.map((item) => (
                  <li key={item.chapter_id}>
                    {chapterLabel(plan, item.chapter_id)}：{item.characters} 字
                  </li>
                ))}
              </ul>
              <p>
                合计 {preview.total_characters} / {preview.max_total_characters}{" "}
                字，{preview.chapters.length} / {preview.max_chapters}{" "}
                章；将一并发送 {preview.characters} 个人物的名字、
                {preview.events} 个已有事件和 {preview.open_states}{" "}
                个仍有效的人物状态
                {preview.events_omitted || preview.states_omitted
                  ? `（另有 ${preview.events_omitted} 个较早的事件、${preview.states_omitted} 个状态超出上限未发送）`
                  : ""}
                。
              </p>
              {preview.problem ? (
                <p role="alert">{RANGE_PROBLEMS[preview.problem]}</p>
              ) : null}
              <label className="story-control__field">
                <span>提取要求（可选，最多 500 字）</span>
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
                disabled={
                  !profileId || Boolean(busy) || preview.problem !== null
                }
                onClick={() => void prepare()}
              >
                准备提取（冻结正文，不调用模型）
              </button>
            </div>
          ) : null}
        </div>
      ) : null}

      {extraction?.status === "ready" ? (
        <div>
          <p>
            已冻结 {extraction.chapters.length} 章正文，共{" "}
            {extraction.total_characters} 字，以及{" "}
            {extraction.characters.length} 个人物、{extraction.events.length}{" "}
            个事件和 {extraction.states.length} 个仍有效的人物状态。模型：
            {extraction.model_name}。
          </p>
          <details>
            <summary>查看将发送的完整内容</summary>
            <pre className="story-control__preview">
              {extraction.request_preview}
            </pre>
          </details>
          <OperationSendGuard
            loadEstimate={loadEstimate}
            refreshKey={`${extraction.id}:${extraction.version}`}
          >
            {(allowed) => (
              <div>
                {extraction.model_kind === "cloud" ? (
                  <label>
                    <input
                      type="checkbox"
                      checked={consent}
                      onChange={(event) => setConsent(event.target.checked)}
                    />
                    同意把上述章节正文发送给云端模型
                  </label>
                ) : null}
                <button
                  type="button"
                  disabled={
                    !allowed ||
                    Boolean(busy) ||
                    (extraction.model_kind === "cloud" && !consent)
                  }
                  onClick={() => void send()}
                >
                  发送一次，生成事件与人物状态证据卡
                </button>
              </div>
            )}
          </OperationSendGuard>
          <button type="button" onClick={reset}>
            放弃本次准备
          </button>
        </div>
      ) : null}

      {extraction?.status === "running" ? (
        <p role="status">该提取正在进行中或曾被中断，请稍后刷新查看结果。</p>
      ) : null}

      {extraction?.status === "failed" ? (
        <div role="alert">
          <p>
            {extraction.error === "TimelineOutputInvalid"
              ? "模型回复不是有效的证据卡格式，未生成证据卡，时间线未改变。原始回复已保留，系统不会自动重试。"
              : "本次提取失败，时间线未改变；系统不会自动重试。"}
          </p>
          {extraction.evidence !== null ? (
            <details>
              <summary>
                查看原始回复{extraction.evidence_truncated ? "（已截断）" : ""}
              </summary>
              <pre className="story-control__preview">
                {extraction.evidence}
              </pre>
            </details>
          ) : null}
          <button type="button" onClick={reset}>
            重新准备
          </button>
        </div>
      ) : null}

      {extraction?.status === "completed" ? (
        <div>
          {extraction.summary ? <p>模型判断：{extraction.summary}</p> : null}
          {extraction.cards.length === 0 ? (
            <p>模型没有给出证据卡；时间线未改变。</p>
          ) : (
            <ul className="story-control__list">
              {extraction.cards.map((card, index) => {
                const check = extraction.checks[index];
                return (
                  <li key={index}>
                    <label>
                      <input
                        type="checkbox"
                        aria-label={`选择事件或人物状态卡 ${index + 1}`}
                        disabled={
                          !check.valid || adopted.has(index) || Boolean(busy)
                        }
                        checked={adopted.has(index) || selected.includes(index)}
                        onChange={() => toggleCard(index)}
                      />
                      <CardBody
                        plan={plan}
                        extraction={extraction}
                        card={card}
                        check={check}
                      />
                      {adopted.has(index) ? " · 已采用" : ""}
                    </label>
                  </li>
                );
              })}
            </ul>
          )}
          {stale ? (
            <button type="button" onClick={reset}>
              重新准备提取
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
            另起一次提取
          </button>
        </div>
      ) : null}
      <button type="button" onClick={onClose}>
        关闭事件与人物状态提取
      </button>
    </section>
  );
}
