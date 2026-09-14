import { type FormEvent, useEffect, useRef, useState } from "react";

import {
  STORY_BIBLE_CONTENT_MAX_CODE_POINTS,
  STORY_BIBLE_TITLE_MAX_CODE_POINTS,
} from "../constants";
import type { StoryBibleController } from "../hooks/useStoryBible";
import {
  countStoryBibleCodePoints,
  errorForStoryBibleField,
  validateStoryBibleInput,
  type StoryBibleFieldError,
  type StoryBibleFieldName,
} from "../validation";

export function StoryBibleEditor({
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
  const ready = state.status === "ready" ? state : null;
  const saveKind = ready?.save.kind ?? "idle";

  useEffect(() => {
    if (ready?.save.kind === "save_error") {
      feedbackRef.current?.focus();
    }
    if (
      saveKind === "success" ||
      saveKind === "adopted_latest" ||
      saveKind === "rebased_draft" ||
      saveKind === "discarded_draft"
    ) {
      feedbackRef.current?.focus();
    }
  }, [ready?.save, saveKind]);

  if (ready === null) {
    return null;
  }
  const effectiveFieldErrors =
    fieldErrors.length > 0
      ? fieldErrors
      : ready.save.kind === "save_error"
        ? ready.save.error.fieldErrors
        : [];
  const titleError = errorForStoryBibleField(effectiveFieldErrors, "title");
  const contentError = errorForStoryBibleField(effectiveFieldErrors, "content");
  const blocked =
    ready.save.kind === "saving" || ready.save.kind === "resolution";

  const clearFieldError = (field: StoryBibleFieldName): void => {
    setFieldErrors((current) =>
      current.filter((error) => error.field !== field),
    );
    controller.dismissFeedback();
  };

  const submit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const errors = validateStoryBibleInput(
      ready.draft.title,
      ready.draft.content,
    );
    if (errors.length > 0) {
      setFieldErrors(errors);
      (errors[0]?.field === "content" ? contentRef : titleRef).current?.focus();
      return;
    }
    setFieldErrors([]);
    void controller.save();
  };

  const feedback =
    ready.save.kind === "success"
      ? "小说设定修订已保存。"
      : ready.save.kind === "save_error"
        ? ready.save.error.message
        : ready.save.kind === "adopted_latest"
          ? "已放弃当前草稿并采用服务器最新版本。"
          : ready.save.kind === "rebased_draft"
            ? "当前草稿将在下次手动保存时完整替换服务器上的标题和正文。"
            : ready.save.kind === "discarded_draft"
              ? "已放弃未保存更改，并恢复当前基线内容。"
              : null;

  return (
    <section
      className="story-bible-editor"
      aria-labelledby="story-bible-editor-title"
    >
      <div className="story-bible-editor__heading">
        <div>
          <p className="section-kicker">完整纯文本替换</p>
          <h3 id="story-bible-editor-title">编辑小说设定</h3>
        </div>
        <p className="story-bible-editor__dirty" role="status">
          {controller.dirty ? "有未保存更改" : "当前没有未保存更改"}
        </p>
      </div>
      <form onSubmit={submit} noValidate>
        <div className="form-field">
          <label htmlFor="story-bible-edit-title">小说设定标题</label>
          <input
            ref={titleRef}
            id="story-bible-edit-title"
            name="title"
            type="text"
            value={ready.draft.title}
            onChange={(event) => {
              controller.setTitle(event.target.value);
              clearFieldError("title");
            }}
            aria-invalid={titleError !== null}
            aria-describedby={`story-bible-edit-title-count${titleError === null ? "" : " story-bible-edit-title-error"}`}
            disabled={blocked}
          />
          <p id="story-bible-edit-title-count" className="field-count">
            {countStoryBibleCodePoints(ready.draft.title)} /{" "}
            {STORY_BIBLE_TITLE_MAX_CODE_POINTS} 字符
          </p>
          {titleError === null ? null : (
            <p id="story-bible-edit-title-error" className="field-error">
              {titleError}
            </p>
          )}
        </div>
        <div className="form-field">
          <label htmlFor="story-bible-edit-content">小说设定正文</label>
          <textarea
            ref={contentRef}
            id="story-bible-edit-content"
            name="content"
            rows={22}
            value={ready.draft.content}
            onChange={(event) => {
              controller.setContent(event.target.value);
              clearFieldError("content");
            }}
            aria-invalid={contentError !== null}
            aria-describedby={`story-bible-edit-content-count${contentError === null ? "" : " story-bible-edit-content-error"}`}
            disabled={blocked}
          />
          <p id="story-bible-edit-content-count" className="field-count">
            {countStoryBibleCodePoints(ready.draft.content)} /{" "}
            {STORY_BIBLE_CONTENT_MAX_CODE_POINTS} 字符
          </p>
          {contentError === null ? null : (
            <p id="story-bible-edit-content-error" className="field-error">
              {contentError}
            </p>
          )}
        </div>
        <div className="story-bible-editor__actions">
          <button type="submit" disabled={blocked || !controller.dirty}>
            {ready.save.kind === "saving" ? "正在保存修订…" : "保存完整修订"}
          </button>
          <button
            type="button"
            className="button-secondary"
            disabled={blocked || !controller.dirty}
            onClick={controller.discardDraft}
          >
            放弃未保存更改
          </button>
        </div>
      </form>
      {feedback === null ? null : (
        <div
          ref={feedbackRef}
          className={`story-bible-feedback story-bible-feedback--${ready.save.kind}`}
          role={ready.save.kind === "save_error" ? "alert" : "status"}
          aria-live={ready.save.kind === "save_error" ? "assertive" : "polite"}
          tabIndex={-1}
        >
          <p>{feedback}</p>
          {ready.save.kind === "save_error" &&
          ready.save.error.requestId !== null ? (
            <p className="request-id">请求编号：{ready.save.error.requestId}</p>
          ) : null}
        </div>
      )}
    </section>
  );
}
