import { type FormEvent, useEffect, useRef, useState } from "react";

import type { ProjectFieldError, ProjectFieldName } from "../api/errors";
import {
  PROJECT_DESCRIPTION_MAX_CODE_POINTS,
  PROJECT_TITLE_MAX_CODE_POINTS,
} from "../constants";
import { countUnicodeCodePoints } from "../formatting";
import type { ReviseProjectController } from "../hooks/useReviseProject";
import { errorForProjectField, validateProjectInput } from "../validation";

interface ProjectEditFormProps {
  readonly controller: ReviseProjectController;
  readonly onReloadProject: () => void;
}

export function ProjectEditForm({
  controller,
  onReloadProject,
}: ProjectEditFormProps) {
  const [fieldErrors, setFieldErrors] = useState<readonly ProjectFieldError[]>(
    [],
  );
  const titleRef = useRef<HTMLInputElement>(null);
  const descriptionRef = useRef<HTMLTextAreaElement>(null);
  const feedbackRef = useRef<HTMLDivElement>(null);
  const titleError = errorForProjectField(fieldErrors, "title");
  const descriptionError = errorForProjectField(fieldErrors, "description");
  const state = controller.state;
  const blocked =
    state.kind === "saving" ||
    state.kind === "conflict" ||
    state.kind === "outcome_unknown";

  useEffect(() => {
    if (
      state.kind === "success" ||
      state.kind === "adopted_latest" ||
      state.kind === "rebased_draft"
    ) {
      feedbackRef.current?.focus();
    }
  }, [state.kind]);

  useEffect(() => {
    if (state.kind !== "save_error") return;
    if (titleError !== null) titleRef.current?.focus();
    else if (descriptionError !== null) descriptionRef.current?.focus();
    else feedbackRef.current?.focus();
  }, [descriptionError, state.kind, titleError]);

  const clearFieldError = (field: ProjectFieldName): void => {
    setFieldErrors((current) =>
      current.filter((error) => error.field !== field),
    );
    controller.dismissFeedback();
  };

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    const clientErrors = validateProjectInput(
      controller.draft.title,
      controller.draft.description,
    );
    if (clientErrors.length > 0) {
      setFieldErrors(clientErrors);
      (clientErrors[0]?.field === "description"
        ? descriptionRef
        : titleRef
      ).current?.focus();
      return;
    }
    setFieldErrors([]);
    const result = await controller.save();
    if (result.kind === "error") setFieldErrors(result.error.fieldErrors);
  };

  const feedback =
    state.kind === "success"
      ? "小说信息已保存。"
      : state.kind === "save_error"
        ? state.error.message
        : state.kind === "outcome_unknown"
          ? state.error.message
          : state.kind === "adopted_latest"
            ? "已采用最新保存版本。"
            : state.kind === "rebased_draft"
              ? "当前编辑内容将在下次保存时应用到最新版本。"
              : null;

  return (
    <section className="project-edit" aria-labelledby="project-edit-title">
      <div className="project-edit__heading">
        <div>
          <p className="section-kicker">小说信息</p>
          <h3 id="project-edit-title">编辑书名与简介</h3>
        </div>
        <p className="project-edit__dirty" role="status">
          {controller.dirty ? "有未保存更改" : "已保存"}
        </p>
      </div>
      <form
        onSubmit={(event) => void submit(event)}
        noValidate
        autoComplete="off"
      >
        <div className="form-field">
          <label htmlFor="project-edit-title-input">书名</label>
          <input
            ref={titleRef}
            id="project-edit-title-input"
            name="edit-novel-title"
            type="text"
            autoComplete="off"
            value={controller.draft.title}
            onChange={(event) => {
              controller.setTitle(event.target.value);
              clearFieldError("title");
            }}
            aria-invalid={titleError !== null}
            aria-describedby={`project-edit-title-count${titleError === null ? "" : " project-edit-title-error"}`}
            disabled={blocked}
          />
          <p id="project-edit-title-count" className="field-count">
            {countUnicodeCodePoints(controller.draft.title)} /{" "}
            {PROJECT_TITLE_MAX_CODE_POINTS} 字符
          </p>
          {titleError === null ? null : (
            <p id="project-edit-title-error" className="field-error">
              {titleError}
            </p>
          )}
        </div>
        <div className="form-field">
          <label htmlFor="project-edit-description">简介</label>
          <textarea
            ref={descriptionRef}
            id="project-edit-description"
            name="edit-novel-description"
            autoComplete="off"
            rows={8}
            value={controller.draft.description}
            onChange={(event) => {
              controller.setDescription(event.target.value);
              clearFieldError("description");
            }}
            aria-invalid={descriptionError !== null}
            aria-describedby={`project-edit-description-count${descriptionError === null ? "" : " project-edit-description-error"}`}
            disabled={blocked}
          />
          <p id="project-edit-description-count" className="field-count">
            {countUnicodeCodePoints(controller.draft.description)} /{" "}
            {PROJECT_DESCRIPTION_MAX_CODE_POINTS} 字符
          </p>
          {descriptionError === null ? null : (
            <p id="project-edit-description-error" className="field-error">
              {descriptionError}
            </p>
          )}
        </div>
        <button type="submit" disabled={blocked || !controller.dirty}>
          {state.kind === "saving" ? "正在保存…" : "保存小说信息"}
        </button>
      </form>
      {feedback === null ? null : (
        <div
          ref={feedbackRef}
          className={`project-edit__feedback project-edit__feedback--${state.kind}`}
          role={
            state.kind === "save_error" || state.kind === "outcome_unknown"
              ? "alert"
              : "status"
          }
          aria-live={
            state.kind === "save_error" || state.kind === "outcome_unknown"
              ? "assertive"
              : "polite"
          }
          tabIndex={-1}
        >
          <p>{feedback}</p>
          {state.kind === "save_error" && state.error.requestId !== null ? (
            <p className="request-id">请求编号：{state.error.requestId}</p>
          ) : null}
          {state.kind === "outcome_unknown" ? (
            <button type="button" onClick={onReloadProject}>
              重新加载小说
            </button>
          ) : null}
        </div>
      )}
    </section>
  );
}
