import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router";

import type { CharacterListController } from "../hooks/useCharacterList";
import { characterEditorPath } from "../routing";
import {
  errorForCharacterField,
  validateCharacterInput,
  type CharacterFieldError,
  type CharacterFieldName,
} from "../validation";

export function CharacterCreateForm({
  projectId,
  controller,
}: {
  readonly projectId: string;
  readonly controller: CharacterListController;
}) {
  const [errors, setErrors] = useState<readonly CharacterFieldError[]>([]);
  const nameRef = useRef<HTMLInputElement>(null);
  const roleRef = useRef<HTMLInputElement>(null);
  const profileRef = useRef<HTMLTextAreaElement>(null);
  const feedbackRef = useRef<HTMLDivElement>(null);
  const create = controller.createState;
  const listReady =
    controller.state.status === "ready" || controller.state.status === "empty";

  useEffect(() => {
    if (
      create.status === "success" ||
      create.status === "error" ||
      create.status === "outcome_unknown"
    )
      feedbackRef.current?.focus();
  }, [create]);

  if (!listReady) return null;
  const effectiveErrors =
    errors.length > 0
      ? errors
      : create.status === "error"
        ? create.error.fieldErrors
        : [];

  const clear = (field: CharacterFieldName): void => {
    setErrors((current) => current.filter((error) => error.field !== field));
    controller.dismissCreateFeedback();
  };

  const submit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const next = validateCharacterInput(
      controller.draft.name,
      controller.draft.role,
      controller.draft.profile,
    );
    if (next.length > 0) {
      setErrors(next);
      const refs = { name: nameRef, role: roleRef, profile: profileRef };
      refs[next[0].field].current?.focus();
      return;
    }
    setErrors([]);
    void controller.create();
  };

  return (
    <section className="character-form" aria-labelledby="character-create-title">
      <h2 id="character-create-title">创建角色</h2>
      <form onSubmit={submit} noValidate autoComplete="off">
        <div className="form-field">
          <label htmlFor="character-create-name">角色名称</label>
          <input
            ref={nameRef}
            id="character-create-name"
            name="new-character-name"
            autoComplete="off"
            value={controller.draft.name}
            onChange={(event) => {
              controller.setDraftField("name", event.target.value);
              clear("name");
            }}
            aria-invalid={errorForCharacterField(effectiveErrors, "name") !== null}
            aria-describedby="character-create-name-error"
            disabled={create.status === "submitting"}
          />
          <p id="character-create-name-error" className="field-error">
            {errorForCharacterField(effectiveErrors, "name")}
          </p>
        </div>
        <div className="form-field">
          <label htmlFor="character-create-role">角色定位</label>
          <input
            ref={roleRef}
            id="character-create-role"
            name="new-character-role"
            autoComplete="off"
            value={controller.draft.role}
            onChange={(event) => {
              controller.setDraftField("role", event.target.value);
              clear("role");
            }}
            aria-invalid={errorForCharacterField(effectiveErrors, "role") !== null}
            aria-describedby="character-create-role-error"
            disabled={create.status === "submitting"}
          />
          <p id="character-create-role-error" className="field-error">
            {errorForCharacterField(effectiveErrors, "role")}
          </p>
        </div>
        <div className="form-field">
          <label htmlFor="character-create-profile">角色档案（纯文本）</label>
          <textarea
            ref={profileRef}
            id="character-create-profile"
            name="new-character-profile"
            autoComplete="off"
            rows={8}
            value={controller.draft.profile}
            onChange={(event) => {
              controller.setDraftField("profile", event.target.value);
              clear("profile");
            }}
            aria-invalid={errorForCharacterField(effectiveErrors, "profile") !== null}
            aria-describedby="character-create-profile-error"
            disabled={create.status === "submitting"}
          />
          <p id="character-create-profile-error" className="field-error">
            {errorForCharacterField(effectiveErrors, "profile")}
          </p>
        </div>
        <button
          type="submit"
          disabled={
            create.status === "submitting" ||
            (create.status === "outcome_unknown" && !create.resubmitConfirmed)
          }
        >
          {create.status === "submitting" ? "正在创建…" : "创建角色"}
        </button>
      </form>
      {create.status === "idle" || create.status === "submitting" ? null : (
        <div
          ref={feedbackRef}
          tabIndex={-1}
          role={create.status === "success" ? "status" : "alert"}
          aria-live={create.status === "success" ? "polite" : "assertive"}
          className="character-feedback"
        >
          {create.status === "success" ? (
            <>
              <p>角色创建成功。</p>
              <Link to={characterEditorPath(projectId, create.characterId)}>查看新角色</Link>
            </>
          ) : create.status === "error" ? (
            <p>{create.error.message}</p>
          ) : (
            <>
              <p>{create.error.message}</p>
              <button type="button" onClick={() => void controller.reloadFirstPage()}>
                重新读取角色列表
              </button>
              <p>再次提交可能创建重复角色，请先人工核对列表。</p>
              <button type="button" onClick={controller.confirmResubmit}>
                我已确认需要再次提交
              </button>
            </>
          )}
        </div>
      )}
    </section>
  );
}
