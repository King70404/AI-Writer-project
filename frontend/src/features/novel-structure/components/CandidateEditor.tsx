import { useEffect, useState } from "react";
import type { WorkflowCandidate } from "../api/ai-workflow";
import { MAX_EDIT_CHARACTERS, visibleCharacters } from "../candidate-edit";

/**
 * 作者编辑候选（B2）。保存的是候选的新版本（作者来源、不可变），既不写入正文，也不
 * 修改模型原始候选；采用仍需作者另外点击。未保存的修改只在本页保留。
 */
export function CandidateEditor({
  candidate,
  savedRevisionId,
  disabled,
  onSave,
  onDirtyChange,
}: {
  readonly candidate: WorkflowCandidate;
  readonly savedRevisionId: string;
  readonly disabled: boolean;
  readonly onSave: (text: string) => Promise<boolean>;
  readonly onDirtyChange: (dirty: boolean) => void;
}) {
  const latest = candidate.latest_edit;
  const baseline = latest?.text ?? candidate.text;
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(baseline);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const dirty = open && draft !== baseline;
  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);
  const count = visibleCharacters(draft);
  const invalid = count === 0 || count > MAX_EDIT_CHARACTERS;
  const stale = latest !== null && latest.base_revision_id !== savedRevisionId;
  const save = async (text: string) => {
    setSaving(true);
    setNotice("");
    try {
      if (await onSave(text)) {
        setOpen(false);
        setNotice("修改已保存为新版本，尚未写入正文。");
      }
    } finally {
      setSaving(false);
    }
  };
  return (
    <section aria-label="编辑候选" className="candidate-editor">
      {latest ? (
        <p role="status">
          已保存作者修改第 {latest.sequence} 版 · {latest.character_count}{" "}
          字。原始模型候选保留不变，可在对照中查看。
        </p>
      ) : null}
      {stale ? (
        <div role="alert">
          <p>
            这版修改是在较早的正文上保存的；正文之后已变化，不能直接采用，避免覆盖新的正文。
          </p>
          <button
            type="button"
            disabled={disabled || saving}
            onClick={() => void save(latest.text)}
          >
            按当前正文重新保存修改
          </button>
        </div>
      ) : null}
      {notice ? <p role="status">{notice}</p> : null}
      {open ? (
        <>
          <label htmlFor={`candidate-edit-${candidate.candidate_id}`}>
            编辑候选文本
          </label>
          <textarea
            id={`candidate-edit-${candidate.candidate_id}`}
            rows={8}
            value={draft}
            maxLength={12000}
            disabled={disabled || saving}
            onChange={(event) => setDraft(event.target.value)}
          />
          <p>
            {count} 字（非空白字符，最多 {MAX_EDIT_CHARACTERS}
            ）。保存只生成候选的新版本， 不写入正文；采用仍需点击下方按钮。
          </p>
          {dirty ? <p>有未保存的修改；保存或放弃后才能采用。</p> : null}
          <button
            type="button"
            disabled={disabled || saving || !dirty || invalid}
            onClick={() => void save(draft)}
          >
            {saving ? "正在保存修改…" : "保存修改"}
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={() => {
              setDraft(baseline);
              setOpen(false);
            }}
          >
            放弃未保存修改
          </button>
        </>
      ) : (
        <button
          type="button"
          disabled={disabled}
          onClick={() => {
            setDraft(baseline);
            setNotice("");
            setOpen(true);
          }}
        >
          {latest ? "继续编辑修改" : "编辑候选"}
        </button>
      )}
    </section>
  );
}
