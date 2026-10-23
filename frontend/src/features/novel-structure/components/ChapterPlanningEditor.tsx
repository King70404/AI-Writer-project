import { useImperativeHandle, useRef, useState, type Ref } from "react";
import {
  characterApiClient,
  type CharacterApiClient,
} from "../../character/api/client";
import type { CharacterListItemResponse } from "../../character/api/contracts";
import {
  preparationError,
  type ChapterPlan,
  type ChapterPlanInput,
  type PlanScene,
  type RuleRevision,
  type WritingPreparationClient,
} from "../api/writing-preparation";

export type AddRuleResult = "added" | "already_selected" | "limit" | "busy";

/** 范文捷径使用：把已确认的规则版本加入本章规划草稿（不自动保存）。 */
export interface ChapterPlanningHandle {
  readonly addRule: (revisionId: string) => AddRuleResult;
}

export function ChapterPlanningEditor({
  ref,
  projectId,
  chapterId,
  plan,
  rules,
  content,
  client,
  onSaved,
  onDirty,
  disabled = false,
  onBusy,
  characterClient = characterApiClient,
}: {
  readonly ref?: Ref<ChapterPlanningHandle>;
  readonly projectId: string;
  readonly chapterId: string;
  readonly plan: ChapterPlan | null;
  readonly rules: readonly RuleRevision[];
  readonly content: string;
  readonly client: WritingPreparationClient;
  readonly onSaved: (plan: ChapterPlan) => void;
  readonly onDirty: (dirty: boolean) => void;
  readonly disabled?: boolean;
  readonly onBusy?: (busy: boolean) => void;
  readonly characterClient?: CharacterApiClient;
}) {
  const [draft, setDraft] = useState<ChapterPlanInput>(
    plan ?? {
      memory_focuses: [""],
      target_characters: 3000,
      chapter_goal: "",
      conflict: "",
      continuity_notes: "",
      scenes: [],
      include_story_bible: false,
      writing_rule_revision_ids: [],
    },
  );
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [characters, setCharacters] = useState<
    readonly CharacterListItemResponse[]
  >([]);
  const [cursor, setCursor] = useState<string | null | undefined>(undefined);
  const [charactersBusy, setCharactersBusy] = useState(false);
  const saving = useRef(false);
  const update = (next: Partial<ChapterPlanInput>) => {
    setDraft({ ...draft, ...next });
    setDirty(true);
    onDirty(true);
  };
  useImperativeHandle(ref, () => ({
    addRule(revisionId: string): AddRuleResult {
      if (busy || disabled) return "busy";
      if (draft.writing_rule_revision_ids.includes(revisionId))
        return "already_selected";
      if (draft.writing_rule_revision_ids.length >= 8) return "limit";
      update({
        writing_rule_revision_ids: [
          ...draft.writing_rule_revision_ids,
          revisionId,
        ],
      });
      return "added";
    },
  }));
  const scene = (index: number, next: Partial<PlanScene>) =>
    update({
      scenes: draft.scenes.map((item, position) =>
        position === index ? { ...item, ...next } : item,
      ),
    });
  const moveScene = (index: number, offset: number) => {
    const scenes = [...draft.scenes];
    [scenes[index], scenes[index + offset]] = [
      scenes[index + offset],
      scenes[index],
    ];
    update({ scenes });
  };
  const loadCharacters = async () => {
    setCharactersBusy(true);
    setError("");
    try {
      const page = await characterClient.listCharacters({
        projectId,
        limit: 100,
        ...(cursor ? { cursor } : {}),
      });
      setCharacters((current) => [...current, ...page.items]);
      setCursor(page.next_cursor);
    } catch {
      setError("人物列表读取失败，已选人物仍保留，请重试读取。");
    } finally {
      setCharactersBusy(false);
    }
  };
  const save = async () => {
    if (saving.current || disabled) return;
    const focuses = draft.memory_focuses
      .map((item) => item.trim())
      .filter(Boolean);
    if (
      !focuses.length ||
      new Set(focuses).size !== focuses.length ||
      !Number.isInteger(draft.target_characters) ||
      draft.target_characters < 200 ||
      draft.target_characters > 20000
    ) {
      setError(
        "请填写 1–3 项不重复的章节重点，目标字数须为 200–20000 的整数。",
      );
      return;
    }
    saving.current = true;
    setBusy(true);
    onBusy?.(true);
    setError("");
    try {
      const saved = await client.savePlan(
        projectId,
        chapterId,
        {
          memory_focuses: focuses,
          target_characters: draft.target_characters,
          chapter_goal: draft.chapter_goal,
          conflict: draft.conflict,
          continuity_notes: draft.continuity_notes,
          scenes: draft.scenes,
          include_story_bible: draft.include_story_bible,
          writing_rule_revision_ids: draft.writing_rule_revision_ids,
        },
        plan?.version ?? 0,
      );
      setDraft(saved);
      setDirty(false);
      onDirty(false);
      onSaved(saved);
    } catch (failure) {
      setError(preparationError(failure).message);
    } finally {
      saving.current = false;
      setBusy(false);
      onBusy?.(false);
    }
  };
  const count = Array.from(content).filter(
    (value) => !/\s/u.test(value),
  ).length;
  return (
    <section aria-label="章节长篇规划">
      <h4>章节规划与连续性</h4>
      <p>
        把长篇拆成章节目标与场景推进。已保存规划和勾选的规则版本会用于下一次准备的
        AI 任务；已有任务保持原快照。
      </p>
      <p role="status">
        {dirty
          ? "规划未保存"
          : plan
            ? `规划已保存 · 版本 ${plan.version}`
            : "尚未建立规划"}
        。正文 {count} / {draft.target_characters} 字（非空白字符）。
      </p>
      {error ? <p role="alert">{error}</p> : null}
      <fieldset disabled={busy || disabled}>
        <legend>本章目标</legend>
        {draft.memory_focuses.map((focus, index) => (
          <label key={index}>
            章节重点 {index + 1}
            <input
              maxLength={200}
              value={focus}
              onChange={(event) =>
                update({
                  memory_focuses: draft.memory_focuses.map((item, position) =>
                    position === index ? event.target.value : item,
                  ),
                })
              }
            />
          </label>
        ))}
        <button
          type="button"
          disabled={draft.memory_focuses.length >= 3}
          onClick={() =>
            update({ memory_focuses: [...draft.memory_focuses, ""] })
          }
        >
          增加章节重点
        </button>
        {draft.memory_focuses.length > 1 ? (
          <button
            type="button"
            onClick={() =>
              update({ memory_focuses: draft.memory_focuses.slice(0, -1) })
            }
          >
            移除最后一项重点
          </button>
        ) : null}
        <label>
          本章目标字数
          <input
            type="number"
            min={200}
            max={20000}
            value={draft.target_characters}
            onChange={(event) =>
              update({ target_characters: Number(event.target.value) })
            }
          />
        </label>
        <label>
          本章要发生的变化
          <textarea
            maxLength={2000}
            rows={2}
            value={draft.chapter_goal}
            onChange={(event) => update({ chapter_goal: event.target.value })}
          />
        </label>
        <label>
          核心冲突
          <textarea
            maxLength={2000}
            rows={2}
            value={draft.conflict}
            onChange={(event) => update({ conflict: event.target.value })}
          />
        </label>
        <label>
          承接前文与后续伏笔
          <textarea
            maxLength={4000}
            rows={3}
            value={draft.continuity_notes}
            onChange={(event) =>
              update({ continuity_notes: event.target.value })
            }
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={draft.include_story_bible}
            onChange={(event) =>
              update({ include_story_bible: event.target.checked })
            }
          />
          关联当前小说设定
        </label>
      </fieldset>
      <fieldset disabled={busy || disabled}>
        <legend>本章使用的写作规则版本</legend>
        <p>
          每个版本保留原内容。修改规则并确认新版本后，请在这里选择，再保存规划。最多选择
          8 份。
        </p>
        {!rules.length ? (
          <p>先在范文分析下确认写作规则，即可用于本章。</p>
        ) : (
          rules.map((item) => (
            <label key={item.id}>
              <input
                type="checkbox"
                data-rule-revision-id={item.id}
                checked={draft.writing_rule_revision_ids.includes(item.id)}
                disabled={
                  !draft.writing_rule_revision_ids.includes(item.id) &&
                  draft.writing_rule_revision_ids.length >= 8
                }
                onChange={(event) =>
                  update({
                    writing_rule_revision_ids: event.target.checked
                      ? [...draft.writing_rule_revision_ids, item.id]
                      : draft.writing_rule_revision_ids.filter(
                          (id) => id !== item.id,
                        ),
                  })
                }
              />
              {item.title} · 版本 {item.version}
            </label>
          ))
        )}
      </fieldset>
      <fieldset disabled={busy || disabled}>
        <legend>场景与情节推进点</legend>
        <p>
          场景按显示顺序推进。每个推进点描述行动及其带来的变化；关联人物使用项目中现有资料。
        </p>
        {cursor !== null ? (
          <button
            type="button"
            disabled={charactersBusy}
            onClick={() => void loadCharacters()}
          >
            {charactersBusy
              ? "正在读取人物…"
              : cursor === undefined
                ? "读取可关联人物"
                : "读取更多人物"}
          </button>
        ) : null}
        {draft.scenes.map((item, index) => (
          <fieldset key={item.id}>
            <legend>场景 {index + 1}</legend>
            <label>
              场景 {index + 1} 名称
              <input
                maxLength={120}
                value={item.title}
                onChange={(event) =>
                  scene(index, { title: event.target.value })
                }
              />
            </label>
            <label>
              场景 {index + 1} 时间地点与氛围
              <textarea
                maxLength={500}
                rows={2}
                value={item.setting}
                onChange={(event) =>
                  scene(index, { setting: event.target.value })
                }
              />
            </label>
            {characters.map((character) => (
              <label key={character.character_id}>
                <input
                  type="checkbox"
                  checked={item.character_ids.includes(character.character_id)}
                  disabled={
                    !item.character_ids.includes(character.character_id) &&
                    item.character_ids.length >= 20
                  }
                  onChange={(event) =>
                    scene(index, {
                      character_ids: event.target.checked
                        ? [...item.character_ids, character.character_id]
                        : item.character_ids.filter(
                            (id) => id !== character.character_id,
                          ),
                    })
                  }
                />
                场景 {index + 1} 人物：{character.name}
              </label>
            ))}
            {item.character_ids.filter(
              (id) =>
                !characters.some((character) => character.character_id === id),
            ).length ? (
              <p>
                此场景已关联 {item.character_ids.length}{" "}
                位人物；读取人物列表后可调整。
              </p>
            ) : null}
            {item.beats.map((beat, beatIndex) => (
              <div key={beat.id}>
                <label>
                  场景 {index + 1} 推进点 {beatIndex + 1} 行动
                  <textarea
                    maxLength={1000}
                    rows={2}
                    value={beat.action}
                    onChange={(event) =>
                      scene(index, {
                        beats: item.beats.map((value, position) =>
                          position === beatIndex
                            ? { ...value, action: event.target.value }
                            : value,
                        ),
                      })
                    }
                  />
                </label>
                <label>
                  场景 {index + 1} 推进点 {beatIndex + 1} 变化
                  <textarea
                    maxLength={1000}
                    rows={2}
                    value={beat.change}
                    onChange={(event) =>
                      scene(index, {
                        beats: item.beats.map((value, position) =>
                          position === beatIndex
                            ? { ...value, change: event.target.value }
                            : value,
                        ),
                      })
                    }
                  />
                </label>
                <button
                  type="button"
                  disabled={beatIndex === 0}
                  onClick={() => {
                    const beats = [...item.beats];
                    [beats[beatIndex - 1], beats[beatIndex]] = [
                      beats[beatIndex],
                      beats[beatIndex - 1],
                    ];
                    scene(index, { beats });
                  }}
                >
                  上移推进点 {beatIndex + 1}
                </button>
                <button
                  type="button"
                  onClick={() =>
                    scene(index, {
                      beats: item.beats.filter((value) => value.id !== beat.id),
                    })
                  }
                >
                  删除推进点 {beatIndex + 1}
                </button>
              </div>
            ))}
            <button
              type="button"
              disabled={item.beats.length >= 12}
              onClick={() =>
                scene(index, {
                  beats: [
                    ...item.beats,
                    { id: crypto.randomUUID(), action: "", change: "" },
                  ],
                })
              }
            >
              为场景 {index + 1} 增加推进点
            </button>
            <button
              type="button"
              disabled={index === 0}
              onClick={() => moveScene(index, -1)}
            >
              上移场景 {index + 1}
            </button>
            <button
              type="button"
              disabled={index === draft.scenes.length - 1}
              onClick={() => moveScene(index, 1)}
            >
              下移场景 {index + 1}
            </button>
            <button
              type="button"
              onClick={() =>
                update({
                  scenes: draft.scenes.filter((value) => value.id !== item.id),
                })
              }
            >
              删除场景 {index + 1}
            </button>
          </fieldset>
        ))}
        <button
          type="button"
          disabled={draft.scenes.length >= 12}
          onClick={() =>
            update({
              scenes: [
                ...draft.scenes,
                {
                  id: crypto.randomUUID(),
                  title: "",
                  setting: "",
                  character_ids: [],
                  beats: [],
                },
              ],
            })
          }
        >
          增加场景
        </button>
      </fieldset>
      <button
        type="button"
        disabled={busy || disabled}
        onClick={() => void save()}
      >
        {busy ? "正在保存规划…" : "保存章节规划"}
      </button>
      <p>
        生成仍按每段 200–300
        字提交候选；逐段确认并保存正文后，可继续下一轮，直到完成本章目标。
      </p>
    </section>
  );
}
