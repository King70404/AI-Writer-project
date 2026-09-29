import { type FormEvent, useEffect, useRef, useState } from "react";

import type { StoryBibleController } from "../hooks/useStoryBible";
import {
  STORY_BIBLE_CONTENT_MAX_CODE_POINTS,
  STORY_BIBLE_TITLE_MAX_CODE_POINTS,
} from "../constants";
import {
  countStoryBibleCodePoints,
  errorForStoryBibleField,
  validateStoryBibleInput,
  type StoryBibleFieldError,
  type StoryBibleFieldName,
} from "../validation";

export function StoryBibleCreateForm({
  controller,
}: {
  readonly controller: StoryBibleController;
}) {
  const state = controller.state;
  const [fieldErrors, setFieldErrors] = useState<
    readonly StoryBibleFieldError[]
  >([]);
  const titleRef = useRef<HTMLInputElement>(null);
  const contentRef = useRef<HTMLTextAreaElement>(null);
  const feedbackRef = useRef<HTMLDivElement>(null);
  const createState = state.status === "create_ready" ? state : null;
  const createKind = createState?.create.kind ?? "idle";

  useEffect(() => {
    if (
      createState?.create.kind === "error" &&
      createState.create.error !== null
    ) {
      feedbackRef.current?.focus();
    }
    if (createKind === "outcome_unknown" || createKind === "already_exists") {
      feedbackRef.current?.focus();
    }
  }, [createKind, createState?.create]);

  if (createState === null) return null;
  const stateDraft = createState.draft;
  const stateCreate = createState.create;
  const effectiveFieldErrors =
    fieldErrors.length > 0
      ? fieldErrors
      : (stateCreate.error?.fieldErrors ?? []);
  const titleError = errorForStoryBibleField(effectiveFieldErrors, "title");
  const contentError = errorForStoryBibleField(effectiveFieldErrors, "content");
  const blocked =
    stateCreate.kind === "submitting" ||
    stateCreate.kind === "outcome_unknown" ||
    stateCreate.kind === "already_exists" ||
    stateCreate.verifying;

  const clearFieldError = (field: StoryBibleFieldName): void => {
    setFieldErrors((current) =>
      current.filter((error) => error.field !== field),
    );
  };

  const submit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const errors = validateStoryBibleInput(
      stateDraft.title,
      stateDraft.content,
    );
    if (errors.length > 0) {
      setFieldErrors(errors);
      (errors[0]?.field === "content" ? contentRef : titleRef).current?.focus();
      return;
    }
    setFieldErrors([]);
    void controller.create();
  };

  return (
    <section
      className="story-bible-create"
      aria-labelledby="story-bible-create-title"
    >
      <p className="section-kicker">小说设定</p>
      <h3 id="story-bible-create-title">创建小说设定</h3>
      <p>在这里记录世界观、力量体系、地点、主线和其他长期设定。</p>
      <form onSubmit={submit} noValidate autoComplete="off">
        <div className="form-field">
          <label htmlFor="story-bible-create-title-input">设定标题</label>
          <input
            ref={titleRef}
            id="story-bible-create-title-input"
            name="novel-setting-title"
            type="text"
            autoComplete="off"
            value={stateDraft.title}
            onChange={(event) => {
              controller.setTitle(event.target.value);
              clearFieldError("title");
            }}
            aria-invalid={titleError !== null}
            aria-describedby={`story-bible-create-title-count${titleError === null ? "" : " story-bible-create-title-error"}`}
            disabled={blocked}
          />
          <p id="story-bible-create-title-count" className="field-count">
            {countStoryBibleCodePoints(stateDraft.title)} /{" "}
            {STORY_BIBLE_TITLE_MAX_CODE_POINTS} 字符
          </p>
          {titleError === null ? null : (
            <p id="story-bible-create-title-error" className="field-error">
              {titleError}
            </p>
          )}
        </div>
        <div className="form-field">
          <label htmlFor="story-bible-create-content">设定正文</label>
          <textarea
            ref={contentRef}
            id="story-bible-create-content"
            name="novel-setting-content"
            autoComplete="off"
            rows={16}
            value={stateDraft.content}
            onChange={(event) => {
              controller.setContent(event.target.value);
              clearFieldError("content");
            }}
            aria-invalid={contentError !== null}
            aria-describedby={`story-bible-create-content-count${contentError === null ? "" : " story-bible-create-content-error"}`}
            disabled={blocked}
          />
          <p id="story-bible-create-content-count" className="field-count">
            {countStoryBibleCodePoints(stateDraft.content)} /{" "}
            {STORY_BIBLE_CONTENT_MAX_CODE_POINTS} 字符
          </p>
          {contentError === null ? null : (
            <p id="story-bible-create-content-error" className="field-error">
              {contentError}
            </p>
          )}
        </div>
        <button type="submit" disabled={blocked}>
          {stateCreate.kind === "submitting" ? "正在创建…" : "创建小说设定"}
        </button>
      </form>
      {stateCreate.error === null ? null : (
        <div
          ref={feedbackRef}
          className="story-bible-feedback story-bible-feedback--error"
          role="alert"
          aria-live="assertive"
          tabIndex={-1}
        >
          <p>{stateCreate.error.message}</p>
          {stateCreate.error.requestId === null ? null : (
            <p className="request-id">
              请求编号：{stateCreate.error.requestId}
            </p>
          )}
          {stateCreate.kind === "outcome_unknown" ||
          stateCreate.kind === "already_exists" ? (
            <button
              type="button"
              disabled={stateCreate.verifying}
              onClick={() => void controller.verifyCreateResult()}
            >
              {stateCreate.verifying ? "正在重新读取…" : "重新读取小说设定"}
            </button>
          ) : null}
          {stateCreate.verificationError === null ? null : (
            <>
              <p>{stateCreate.verificationError.message}</p>
              {stateCreate.verificationError.requestId === null ? null : (
                <p className="request-id">
                  请求编号：{stateCreate.verificationError.requestId}
                </p>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}
