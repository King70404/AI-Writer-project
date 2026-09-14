import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router";

import { isCanonicalPrefixedUlid } from "../../../api/identifiers";
import {
  novelStructureApiClient,
  NovelStructureApiError,
  type NovelStructureApiClient,
} from "../api/client";
import type {
  ChapterResponse,
  PositionedStructureInput,
  StructureTextInput,
  VersionedChapter,
  VersionedOutline,
  VersionedVolume,
  VolumeResponse,
} from "../api/contracts";
import {
  fieldError,
  validateStructureInput,
  type StructureFieldError,
} from "../validation";
import { projectDetailsPath } from "../../projects/routing";
import { chapterWritingPath } from "../routing";

interface NovelStructurePageProps {
  readonly client?: NovelStructureApiClient;
}

interface WorkspaceState {
  readonly status: "loading" | "ready" | "project_not_found" | "error";
  readonly outline: VersionedOutline | null;
  readonly volumes: readonly VolumeResponse[];
  readonly selectedVolume: VersionedVolume | null;
  readonly chapters: readonly ChapterResponse[];
  readonly selectedChapter: VersionedChapter | null;
  readonly error: NovelStructureApiError | null;
}

type BusyAction =
  | "outline"
  | "volume-create"
  | "volume-load"
  | "volume-update"
  | "chapter-create"
  | "chapter-load"
  | "chapter-update"
  | null;

const EMPTY_TEXT: StructureTextInput = { title: "", summary: "" };

// Empty numeric fields are a valid editing state, never an API position.
interface PositionedStructureDraft extends StructureTextInput {
  readonly position: number | "";
}

function safeError(error: unknown): NovelStructureApiError {
  return error instanceof NovelStructureApiError
    ? error
    : new NovelStructureApiError({
        kind: "unknown",
        code: "NOVEL_STRUCTURE_UI_ERROR",
        message: "小说结构请求未能完成，请稍后手动重试。",
      });
}

function maxPosition(items: readonly { readonly position: number }[]): number {
  return items.reduce((maximum, item) => Math.max(maximum, item.position), 0);
}

function replaceById<T>(
  items: readonly T[],
  replacement: T,
  id: (item: T) => string,
): readonly T[] {
  return [...items]
    .map((item) => (id(item) === id(replacement) ? replacement : item))
    .sort(
      (left, right) =>
        (left as { readonly position: number }).position -
        (right as { readonly position: number }).position,
    );
}

function ErrorMessage({
  error,
}: {
  readonly error: NovelStructureApiError | null;
}) {
  if (error === null) return null;
  return (
    <div
      className="novel-structure-feedback novel-structure-feedback--error"
      role="alert"
    >
      <p>{error.message}</p>
      {error.requestId === null ? null : <p>请求编号：{error.requestId}</p>}
    </div>
  );
}

function StructureFields({
  prefix,
  value,
  onChange,
  errors,
  position,
  onPositionChange,
}: {
  readonly prefix: string;
  readonly value: StructureTextInput;
  readonly onChange: (value: StructureTextInput) => void;
  readonly errors: readonly StructureFieldError[];
  readonly position?: number | "";
  readonly onPositionChange?: (value: number | "") => void;
}) {
  const titleError = fieldError(errors, "title");
  const summaryError = fieldError(errors, "summary");
  const positionError = fieldError(errors, "position");
  return (
    <>
      <label htmlFor={`${prefix}-title`}>标题</label>
      <input
        id={`${prefix}-title`}
        value={value.title}
        onChange={(event) => onChange({ ...value, title: event.target.value })}
        aria-invalid={titleError !== null}
        aria-describedby={
          titleError === null ? undefined : `${prefix}-title-error`
        }
      />
      {titleError === null ? null : (
        <p id={`${prefix}-title-error`}>{titleError}</p>
      )}
      <label htmlFor={`${prefix}-summary`}>梗概</label>
      <textarea
        id={`${prefix}-summary`}
        value={value.summary}
        onChange={(event) =>
          onChange({ ...value, summary: event.target.value })
        }
        aria-invalid={summaryError !== null}
        aria-describedby={
          summaryError === null ? undefined : `${prefix}-summary-error`
        }
      />
      {summaryError === null ? null : (
        <p id={`${prefix}-summary-error`}>{summaryError}</p>
      )}
      {position === undefined || onPositionChange === undefined ? null : (
        <>
          <label htmlFor={`${prefix}-position`}>顺序</label>
          <input
            id={`${prefix}-position`}
            type="number"
            min="1"
            step="1"
            value={position}
            onChange={(event) => {
              const next = event.target.valueAsNumber;
              onPositionChange(Number.isFinite(next) ? next : "");
            }}
            aria-invalid={positionError !== null}
            aria-describedby={
              positionError === null ? undefined : `${prefix}-position-error`
            }
          />
          {positionError === null ? null : (
            <p id={`${prefix}-position-error`}>{positionError}</p>
          )}
        </>
      )}
    </>
  );
}

function NovelStructureWorkspace({
  projectId,
  client,
}: {
  readonly projectId: string;
  readonly client: NovelStructureApiClient;
}) {
  const [state, setState] = useState<WorkspaceState>({
    status: "loading",
    outline: null,
    volumes: [],
    selectedVolume: null,
    chapters: [],
    selectedChapter: null,
    error: null,
  });
  const [busy, setBusy] = useState<BusyAction>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [actionError, setActionError] = useState<NovelStructureApiError | null>(
    null,
  );
  const [outlineDraft, setOutlineDraft] =
    useState<StructureTextInput>(EMPTY_TEXT);
  const [newVolume, setNewVolume] = useState<PositionedStructureDraft>({
    ...EMPTY_TEXT,
    position: 1,
  });
  const [volumeDraft, setVolumeDraft] = useState<PositionedStructureDraft>({
    ...EMPTY_TEXT,
    position: 1,
  });
  const [newChapter, setNewChapter] = useState<PositionedStructureDraft>({
    ...EMPTY_TEXT,
    position: 1,
  });
  const [chapterDraft, setChapterDraft] = useState<PositionedStructureDraft>({
    ...EMPTY_TEXT,
    position: 1,
  });
  const [fieldErrors, setFieldErrors] = useState<
    readonly StructureFieldError[]
  >([]);
  const generation = useRef(0);

  const loadVolume = useCallback(
    async (volumeId: string, expectedGeneration = generation.current) => {
      setBusy("volume-load");
      setActionError(null);
      try {
        const [selectedVolume, chapters] = await Promise.all([
          client.getVolume(volumeId, projectId),
          client.listChapters(projectId, volumeId),
        ]);
        const firstChapter = chapters[0];
        const selectedChapter =
          firstChapter === undefined
            ? null
            : await client.getChapter(
                firstChapter.chapter_id,
                projectId,
                volumeId,
              );
        if (generation.current !== expectedGeneration) return;
        setVolumeDraft({
          title: selectedVolume.resource.title,
          summary: selectedVolume.resource.summary,
          position: selectedVolume.resource.position,
        });
        setChapterDraft(
          selectedChapter === null
            ? { ...EMPTY_TEXT, position: 1 }
            : {
                title: selectedChapter.resource.title,
                summary: selectedChapter.resource.summary,
                position: selectedChapter.resource.position,
              },
        );
        setNewChapter({ ...EMPTY_TEXT, position: maxPosition(chapters) + 1 });
        setState((current) => ({
          ...current,
          status: "ready",
          selectedVolume,
          chapters,
          selectedChapter,
          error: null,
        }));
      } catch (error) {
        if (generation.current === expectedGeneration)
          setActionError(safeError(error));
      } finally {
        if (generation.current === expectedGeneration) setBusy(null);
      }
    },
    [client, projectId],
  );

  const reload = useCallback(async () => {
    const currentGeneration = ++generation.current;
    setState((current) => ({ ...current, status: "loading", error: null }));
    setActionError(null);
    setFeedback(null);
    try {
      const outlinePromise = client
        .getOutline(projectId)
        .catch((error: unknown) => {
          const normalized = safeError(error);
          if (normalized.kind === "outline_not_found") return null;
          throw normalized;
        });
      const [outline, volumes] = await Promise.all([
        outlinePromise,
        client.listVolumes(projectId),
      ]);
      if (generation.current !== currentGeneration) return;
      setOutlineDraft(
        outline === null
          ? EMPTY_TEXT
          : {
              title: outline.resource.title,
              summary: outline.resource.summary,
            },
      );
      setNewVolume({ ...EMPTY_TEXT, position: maxPosition(volumes) + 1 });
      setState({
        status: "ready",
        outline,
        volumes,
        selectedVolume: null,
        chapters: [],
        selectedChapter: null,
        error: null,
      });
      const firstVolume = volumes[0];
      if (firstVolume !== undefined)
        await loadVolume(firstVolume.volume_id, currentGeneration);
    } catch (error) {
      if (generation.current !== currentGeneration) return;
      const normalized = safeError(error);
      setState((current) => ({
        ...current,
        status:
          normalized.kind === "project_not_found"
            ? "project_not_found"
            : "error",
        error: normalized,
      }));
    }
  }, [client, loadVolume, projectId]);

  useEffect(() => {
    queueMicrotask(() => void reload());
    return () => {
      generation.current += 1;
    };
  }, [reload]);

  const run = async (
    action: Exclude<BusyAction, null>,
    operation: () => Promise<void>,
  ) => {
    setBusy(action);
    setActionError(null);
    setFeedback(null);
    setFieldErrors([]);
    try {
      await operation();
    } catch (error) {
      setActionError(safeError(error));
    } finally {
      setBusy(null);
    }
  };

  const validate = (
    input: StructureTextInput | PositionedStructureDraft,
  ): boolean => {
    const errors = validateStructureInput(
      input.title,
      input.summary,
      "position" in input ? input.position : undefined,
    );
    setFieldErrors(errors);
    return errors.length === 0;
  };

  const submitOutline = () => {
    if (!validate(outlineDraft)) return;
    void run("outline", async () => {
      const next =
        state.outline === null
          ? await client.createOutline(projectId, outlineDraft)
          : await client.updateOutline(
              state.outline.resource.outline_id,
              projectId,
              outlineDraft,
              state.outline.etag,
            );
      setState((current) => ({ ...current, outline: next }));
      setOutlineDraft({
        title: next.resource.title,
        summary: next.resource.summary,
      });
      setFeedback(state.outline === null ? "大纲已创建。" : "大纲已更新。");
    });
  };

  const submitNewVolume = () => {
    if (!validate(newVolume) || newVolume.position === "") return;
    const input: PositionedStructureInput = {
      ...newVolume,
      position: newVolume.position,
    };
    void run("volume-create", async () => {
      const next = await client.createVolume(projectId, input);
      setState((current) => ({
        ...current,
        volumes: [...current.volumes, next.resource].sort(
          (a, b) => a.position - b.position,
        ),
        selectedVolume: next,
        chapters: [],
        selectedChapter: null,
      }));
      setVolumeDraft({
        title: next.resource.title,
        summary: next.resource.summary,
        position: next.resource.position,
      });
      setNewVolume({
        ...EMPTY_TEXT,
        position: input.position + 1,
      });
      setNewChapter({ ...EMPTY_TEXT, position: 1 });
      setFeedback("卷已创建。已选中新卷。");
    });
  };

  const submitVolume = () => {
    if (
      state.selectedVolume === null ||
      !validate(volumeDraft) ||
      volumeDraft.position === ""
    )
      return;
    const input: PositionedStructureInput = {
      ...volumeDraft,
      position: volumeDraft.position,
    };
    void run("volume-update", async () => {
      const next = await client.updateVolume(
        state.selectedVolume!.resource.volume_id,
        projectId,
        input,
        state.selectedVolume!.etag,
      );
      setState((current) => ({
        ...current,
        volumes: replaceById(
          current.volumes,
          next.resource,
          (item) => item.volume_id,
        ),
        selectedVolume: next,
      }));
      setVolumeDraft({
        title: next.resource.title,
        summary: next.resource.summary,
        position: next.resource.position,
      });
      setFeedback("卷已更新。");
    });
  };

  const submitNewChapter = () => {
    if (
      state.selectedVolume === null ||
      !validate(newChapter) ||
      newChapter.position === ""
    )
      return;
    const input: PositionedStructureInput = {
      ...newChapter,
      position: newChapter.position,
    };
    void run("chapter-create", async () => {
      const volumeId = state.selectedVolume!.resource.volume_id;
      const next = await client.createChapter(projectId, volumeId, input);
      setState((current) => ({
        ...current,
        chapters: [...current.chapters, next.resource].sort(
          (a, b) => a.position - b.position,
        ),
        selectedChapter: next,
      }));
      setChapterDraft({
        title: next.resource.title,
        summary: next.resource.summary,
        position: next.resource.position,
      });
      setNewChapter({
        ...EMPTY_TEXT,
        position: input.position + 1,
      });
      setFeedback("章已创建。已选中新章。");
    });
  };

  const selectChapter = (chapter: ChapterResponse) => {
    const volumeId = state.selectedVolume?.resource.volume_id;
    if (volumeId === undefined) return;
    void run("chapter-load", async () => {
      const next = await client.getChapter(
        chapter.chapter_id,
        projectId,
        volumeId,
      );
      setState((current) => ({ ...current, selectedChapter: next }));
      setChapterDraft({
        title: next.resource.title,
        summary: next.resource.summary,
        position: next.resource.position,
      });
    });
  };

  const submitChapter = () => {
    if (
      state.selectedChapter === null ||
      !validate(chapterDraft) ||
      chapterDraft.position === ""
    )
      return;
    const input: PositionedStructureInput = {
      ...chapterDraft,
      position: chapterDraft.position,
    };
    void run("chapter-update", async () => {
      const next = await client.updateChapter(
        state.selectedChapter!.resource.chapter_id,
        projectId,
        state.selectedChapter!.resource.volume_id,
        input,
        state.selectedChapter!.etag,
      );
      setState((current) => ({
        ...current,
        chapters: replaceById(
          current.chapters,
          next.resource,
          (item) => item.chapter_id,
        ),
        selectedChapter: next,
      }));
      setChapterDraft({
        title: next.resource.title,
        summary: next.resource.summary,
        position: next.resource.position,
      });
      setFeedback("章已更新。");
    });
  };

  const outlineErrors = useMemo(
    () => (busy === "outline" ? [] : fieldErrors),
    [busy, fieldErrors],
  );

  if (state.status === "loading")
    return (
      <section className="novel-structure-state" aria-live="polite">
        <h3>正在加载小说结构</h3>
        <p>正在读取大纲、卷和章。</p>
      </section>
    );
  if (state.status === "project_not_found")
    return (
      <section className="novel-structure-state">
        <h3>项目不存在</h3>
        <p>无法为不存在的Project打开小说结构。</p>
        <Link to="/projects">返回小说列表</Link>
      </section>
    );
  if (state.status === "error")
    return (
      <section className="novel-structure-state">
        <h3>小说结构加载失败</h3>
        <ErrorMessage error={state.error} />
        <button type="button" onClick={() => void reload()}>
          重新加载
        </button>
      </section>
    );

  return (
    <div className="novel-structure-workspace">
      <ErrorMessage error={actionError} />
      {feedback === null ? null : (
        <p className="novel-structure-feedback" role="status">
          {feedback}
        </p>
      )}
      <section
        className="novel-structure-panel"
        aria-labelledby="outline-heading"
      >
        <h3 id="outline-heading">大纲</h3>
        <p>
          {state.outline === null
            ? "当前尚未创建大纲。"
            : `当前修订 ${state.outline.version}`}
        </p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            submitOutline();
          }}
        >
          <StructureFields
            prefix="outline"
            value={outlineDraft}
            onChange={setOutlineDraft}
            errors={outlineErrors}
          />
          <button type="submit" disabled={busy !== null}>
            {busy === "outline"
              ? "正在提交…"
              : state.outline === null
                ? "创建大纲"
                : "保存大纲"}
          </button>
        </form>
      </section>

      <section
        className="novel-structure-panel"
        aria-labelledby="volumes-heading"
      >
        <h3 id="volumes-heading">卷</h3>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            submitNewVolume();
          }}
        >
          <h4>创建卷</h4>
          <StructureFields
            prefix="new-volume"
            value={newVolume}
            onChange={(value) =>
              setNewVolume((current) => ({ ...current, ...value }))
            }
            errors={fieldErrors}
            position={newVolume.position}
            onPositionChange={(position) =>
              setNewVolume((current) => ({ ...current, position }))
            }
          />
          <button type="submit" disabled={busy !== null}>
            {busy === "volume-create" ? "正在创建…" : "创建卷"}
          </button>
        </form>
        {state.volumes.length === 0 ? (
          <p>当前尚未创建卷。</p>
        ) : (
          <ol className="novel-structure-list">
            {state.volumes.map((volume) => (
              <li key={volume.volume_id}>
                <button
                  type="button"
                  aria-pressed={
                    state.selectedVolume?.resource.volume_id ===
                    volume.volume_id
                  }
                  disabled={busy !== null}
                  onClick={() => void loadVolume(volume.volume_id)}
                >
                  {volume.position}. {volume.title}
                </button>
              </li>
            ))}
          </ol>
        )}
        {state.selectedVolume === null ? null : (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              submitVolume();
            }}
          >
            <h4>编辑所选卷</h4>
            <StructureFields
              prefix="edit-volume"
              value={volumeDraft}
              onChange={(value) =>
                setVolumeDraft((current) => ({ ...current, ...value }))
              }
              errors={fieldErrors}
              position={volumeDraft.position}
              onPositionChange={(position) =>
                setVolumeDraft((current) => ({ ...current, position }))
              }
            />
            <button type="submit" disabled={busy !== null}>
              {busy === "volume-update" ? "正在保存…" : "保存卷"}
            </button>
          </form>
        )}
      </section>

      <section
        className="novel-structure-panel"
        aria-labelledby="chapters-heading"
      >
        <h3 id="chapters-heading">章</h3>
        {state.selectedVolume === null ? (
          <p>请先创建卷</p>
        ) : (
          <>
            <p>当前卷：{state.selectedVolume.resource.title}</p>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                submitNewChapter();
              }}
            >
              <h4>创建章</h4>
              <StructureFields
                prefix="new-chapter"
                value={newChapter}
                onChange={(value) =>
                  setNewChapter((current) => ({ ...current, ...value }))
                }
                errors={fieldErrors}
                position={newChapter.position}
                onPositionChange={(position) =>
                  setNewChapter((current) => ({ ...current, position }))
                }
              />
              <button type="submit" disabled={busy !== null}>
                {busy === "chapter-create" ? "正在创建…" : "创建章"}
              </button>
            </form>
            {state.chapters.length === 0 ? (
              <p>当前卷尚未创建章。</p>
            ) : (
              <ol className="novel-structure-list">
                {state.chapters.map((chapter) => (
                  <li key={chapter.chapter_id}>
                    <Link
                      to={chapterWritingPath(projectId, chapter.chapter_id)}
                    >
                      写正文
                    </Link>
                    <button
                      type="button"
                      aria-pressed={
                        state.selectedChapter?.resource.chapter_id ===
                        chapter.chapter_id
                      }
                      disabled={busy !== null}
                      onClick={() => selectChapter(chapter)}
                    >
                      {chapter.position}. {chapter.title}
                    </button>
                  </li>
                ))}
              </ol>
            )}
            {state.selectedChapter === null ? null : (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  submitChapter();
                }}
              >
                <h4>编辑所选章</h4>
                <StructureFields
                  prefix="edit-chapter"
                  value={chapterDraft}
                  onChange={(value) =>
                    setChapterDraft((current) => ({ ...current, ...value }))
                  }
                  errors={fieldErrors}
                  position={chapterDraft.position}
                  onPositionChange={(position) =>
                    setChapterDraft((current) => ({ ...current, position }))
                  }
                />
                <button type="submit" disabled={busy !== null}>
                  {busy === "chapter-update" ? "正在保存…" : "保存章"}
                </button>
              </form>
            )}
          </>
        )}
      </section>
    </div>
  );
}

export function NovelStructurePage({
  client = novelStructureApiClient,
}: NovelStructurePageProps) {
  const { projectId } = useParams<{ projectId: string }>();
  const validProjectId = isCanonicalPrefixedUlid(projectId, "prj");
  return (
    <section
      className="novel-structure-page"
      aria-labelledby="novel-structure-title"
    >
      <header className="novel-structure-page__header">
        <div>
          <p className="section-kicker">Novel Structure · 大纲 / 卷 / 章</p>
          <h2 id="novel-structure-title">小说结构</h2>
        </div>
        <div className="novel-structure-page__links">
          {validProjectId ? (
            <Link to={projectDetailsPath(projectId)}>返回小说详情</Link>
          ) : null}
          <Link to="/projects">返回小说列表</Link>
        </div>
      </header>
      {validProjectId ? (
        <NovelStructureWorkspace
          key={projectId}
          projectId={projectId}
          client={client}
        />
      ) : (
        <section className="novel-structure-state">
          <h3>Project编号无效</h3>
          <p>请从项目列表进入小说结构工作区。</p>
        </section>
      )}
    </section>
  );
}
