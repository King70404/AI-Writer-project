import { type FormEvent, useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import type { ProjectApiClient } from "../api/client";
import type { ProjectFieldError, ProjectFieldName } from "../api/errors";
import {
  PROJECT_DESCRIPTION_MAX_CODE_POINTS,
  PROJECT_TITLE_MAX_CODE_POINTS,
} from "../constants";
import { countUnicodeCodePoints } from "../formatting";
import { useCreateProject } from "../hooks/useCreateProject";
import { projectDetailsPath } from "../routing";
import { errorForProjectField, validateProjectInput } from "../validation";

interface CreateProjectFormProps {
  readonly client: ProjectApiClient;
  readonly reloadProjects: () => Promise<boolean>;
}

export function CreateProjectForm({ client, reloadProjects }: CreateProjectFormProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [fieldErrors, setFieldErrors] = useState<readonly ProjectFieldError[]>([]);
  const titleRef = useRef<HTMLInputElement>(null);
  const descriptionRef = useRef<HTMLTextAreaElement>(null);
  const feedbackRef = useRef<HTMLDivElement>(null);
  const create = useCreateProject(reloadProjects, client);
  const titleError = errorForProjectField(fieldErrors, "title");
  const descriptionError = errorForProjectField(fieldErrors, "description");

  useEffect(() => {
    if (create.state.kind === "success" || create.state.kind === "partial_success") {
      feedbackRef.current?.focus();
    }
  }, [create.state.kind]);

  useEffect(() => {
    if (create.state.kind !== "error") return;
    if (titleError !== null) titleRef.current?.focus();
    else if (descriptionError !== null) descriptionRef.current?.focus();
    else feedbackRef.current?.focus();
  }, [create.state.kind, descriptionError, titleError]);

  const clearFieldError = (field: ProjectFieldName): void => {
    setFieldErrors((current) => current.filter((error) => error.field !== field));
    if (create.state.kind === "error") create.dismissFeedback();
  };

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    const clientErrors = validateProjectInput(title, description);
    if (clientErrors.length > 0) {
      setFieldErrors(clientErrors);
      (clientErrors[0]?.field === "description" ? descriptionRef : titleRef).current?.focus();
      return;
    }
    setFieldErrors([]);
    const result = await create.submit({ title, description });
    if (result.kind === "success" || result.kind === "partial_success") {
      setTitle("");
      setDescription("");
      return;
    }
    if (result.kind === "error") setFieldErrors(result.error.fieldErrors);
  };

  const submitting = create.state.kind === "submitting";
  const feedback =
    create.state.kind === "success"
      ? `小说《${create.state.project.title}》已创建。`
      : create.state.kind === "partial_success"
        ? `小说《${create.state.project.title}》已创建，但列表刷新失败。`
        : create.state.kind === "error"
          ? create.state.error.message
          : null;

  return (
    <section className="create-project" aria-labelledby="create-project-title">
      <div>
        <p className="section-kicker">开始一个新故事</p>
        <h3 id="create-project-title">新建小说</h3>
      </div>
      <form onSubmit={(event) => void submit(event)} noValidate autoComplete="off">
        <div className="form-field">
          <label htmlFor="project-title">书名</label>
          <input
            ref={titleRef}
            id="project-title"
            name="novel-title"
            type="text"
            autoComplete="off"
            value={title}
            onChange={(event) => {
              setTitle(event.target.value);
              clearFieldError("title");
            }}
            aria-invalid={titleError !== null}
            aria-describedby={`project-title-count${titleError === null ? "" : " project-title-error"}`}
            disabled={submitting}
          />
          <p id="project-title-count" className="field-count">
            {countUnicodeCodePoints(title)} / {PROJECT_TITLE_MAX_CODE_POINTS} 字符
          </p>
          {titleError === null ? null : <p id="project-title-error" className="field-error">{titleError}</p>}
        </div>
        <div className="form-field">
          <label htmlFor="project-description">一句话简介（可选）</label>
          <textarea
            ref={descriptionRef}
            id="project-description"
            name="novel-description"
            autoComplete="off"
            rows={6}
            value={description}
            onChange={(event) => {
              setDescription(event.target.value);
              clearFieldError("description");
            }}
            aria-invalid={descriptionError !== null}
            aria-describedby={`project-description-count${descriptionError === null ? "" : " project-description-error"}`}
            disabled={submitting}
          />
          <p id="project-description-count" className="field-count">
            {countUnicodeCodePoints(description)} / {PROJECT_DESCRIPTION_MAX_CODE_POINTS} 字符
          </p>
          {descriptionError === null ? null : <p id="project-description-error" className="field-error">{descriptionError}</p>}
        </div>
        <button type="submit" disabled={submitting}>
          {submitting ? "正在创建…" : "创建小说"}
        </button>
      </form>
      {feedback === null ? null : (
        <div
          ref={feedbackRef}
          className={`create-project__feedback create-project__feedback--${create.state.kind}`}
          role={create.state.kind === "error" ? "alert" : "status"}
          aria-live={create.state.kind === "error" ? "assertive" : "polite"}
          tabIndex={-1}
        >
          <p>{feedback}</p>
          {create.state.kind === "success" || create.state.kind === "partial_success" ? (
            <Link to={projectDetailsPath(create.state.project.project_id)}>打开这本小说</Link>
          ) : null}
          {create.state.kind === "error" && create.state.error.requestId !== null ? (
            <p className="request-id">请求编号：{create.state.error.requestId}</p>
          ) : null}
          {create.state.kind === "partial_success" ? (
            <button type="button" onClick={() => void reloadProjects()}>重新加载列表</button>
          ) : null}
        </div>
      )}
    </section>
  );
}
