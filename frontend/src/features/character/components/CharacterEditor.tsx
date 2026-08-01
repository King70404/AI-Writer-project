import { useEffect, useRef, useState, type FormEvent } from "react";

import type { CharacterEditorController } from "../hooks/useCharacterEditor";
import {
  errorForCharacterField,
  validateCharacterInput,
  type CharacterFieldError,
  type CharacterFieldName,
} from "../validation";

export function CharacterEditor({
  controller,
}: {
  readonly controller: CharacterEditorController;
}) {
  const state = controller.state;
  const [errors, setErrors] = useState<readonly CharacterFieldError[]>([]);
  const nameRef = useRef<HTMLInputElement>(null);
  const roleRef = useRef<HTMLInputElement>(null);
  const profileRef = useRef<HTMLTextAreaElement>(null);
  const feedbackRef = useRef<HTMLDivElement>(null);
  const ready = state.status === "ready" ? state : null;

  useEffect(() => {
    if (
      ready !== null &&
      ready.feedback.status !== "idle" &&
      ready.feedback.status !== "saving" &&
      ready.feedback.status !== "resolution"
    )
      feedbackRef.current?.focus();
  }, [ready]);

  if (ready === null) return null;
  const serverErrors =
    ready.feedback.status === "error" ? ready.feedback.error.fieldErrors : [];
  const effective = errors.length > 0 ? errors : serverErrors;
  const blocked =
    ready.feedback.status === "saving" ||
    ready.feedback.status === "resolution";

  const clear = (field: CharacterFieldName): void => {
    setErrors((current) => current.filter((error) => error.field !== field));
    controller.dismissFeedback();
  };
  const submit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const next = validateCharacterInput(
      ready.draft.name,
      ready.draft.role,
      ready.draft.profile,
    );
    if (next.length > 0) {
      setErrors(next);
      const refs = { name: nameRef, role: roleRef, profile: profileRef };
      refs[next[0].field].current?.focus();
      return;
    }
    setErrors([]);
    void controller.save();
  };

  const feedback =
    ready.feedback.status === "success"
      ? "角色修订已保存。"
      : ready.feedback.status === "error"
        ? ready.feedback.error.message
        : ready.feedback.status === "adopted_latest"
          ? "已采用服务器版本，未执行保存。"
          : ready.feedback.status === "rebased_draft"
            ? "草稿已保留并建立最新基线；下次手动保存会完整替换服务器三个字段。"
            : ready.feedback.status === "discarded"
              ? "已放弃未保存更改。"
              : null;

  return (
    <section
      className="character-form"
      aria-labelledby="character-editor-title"
    >
      <h2 id="character-editor-title">编辑当前角色</h2>
      <p role="status">
        {controller.dirty ? "有未保存更改" : "当前没有未保存更改"}
      </p>
      <form onSubmit={submit} noValidate>
        <div className="form-field">
          <label htmlFor="character-edit-name">角色名称</label>
          <input
            ref={nameRef}
            id="character-edit-name"
            value={ready.draft.name}
            onChange={(event) => {
              controller.setDraftField("name", event.target.value);
              clear("name");
            }}
            aria-invalid={errorForCharacterField(effective, "name") !== null}
            aria-describedby="character-edit-name-error"
            disabled={blocked}
          />
          <p id="character-edit-name-error" className="field-error">
            {errorForCharacterField(effective, "name")}
          </p>
        </div>
        <div className="form-field">
          <label htmlFor="character-edit-role">角色定位</label>
          <input
            ref={roleRef}
            id="character-edit-role"
            value={ready.draft.role}
            onChange={(event) => {
              controller.setDraftField("role", event.target.value);
              clear("role");
            }}
            aria-invalid={errorForCharacterField(effective, "role") !== null}
            aria-describedby="character-edit-role-error"
            disabled={blocked}
          />
          <p id="character-edit-role-error" className="field-error">
            {errorForCharacterField(effective, "role")}
          </p>
        </div>
        <div className="form-field">
          <label htmlFor="character-edit-profile">角色档案（纯文本）</label>
          <textarea
            ref={profileRef}
            id="character-edit-profile"
            rows={18}
            value={ready.draft.profile}
            onChange={(event) => {
              controller.setDraftField("profile", event.target.value);
              clear("profile");
            }}
            aria-invalid={errorForCharacterField(effective, "profile") !== null}
            aria-describedby="character-edit-profile-error"
            disabled={blocked}
          />
          <p id="character-edit-profile-error" className="field-error">
            {errorForCharacterField(effective, "profile")}
          </p>
        </div>
        <button type="submit" disabled={blocked || !controller.dirty}>
          {ready.feedback.status === "saving" ? "正在保存…" : "保存"}
        </button>
        <button
          type="button"
          disabled={blocked || !controller.dirty}
          onClick={controller.discard}
        >
          放弃未保存更改
        </button>
      </form>
      {feedback === null ? null : (
        <div
          ref={feedbackRef}
          tabIndex={-1}
          role={ready.feedback.status === "error" ? "alert" : "status"}
          aria-live={ready.feedback.status === "error" ? "assertive" : "polite"}
          className="character-feedback"
        >
          {feedback}
        </div>
      )}
    </section>
  );
}
