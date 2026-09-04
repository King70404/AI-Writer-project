import { useState } from "react";
import { aiWritingClient, type AIWritingClient } from "../api/ai-writing";
import { useAIWriting, type SelectionSnapshot } from "../hooks/useAIWriting";
import type { useChapterWriting } from "../hooks/useChapterWriting";

export function AIWritingAssistant({
  chapterId,
  writing,
  selection,
  client = aiWritingClient,
}: {
  readonly chapterId: string;
  readonly writing: ReturnType<typeof useChapterWriting>;
  readonly selection: SelectionSnapshot | null;
  readonly client?: AIWritingClient;
}) {
  const [instruction, setInstruction] = useState("");
  const ai = useAIWriting(chapterId, writing, client);
  const disabled = ai.status === "generating" || writing.state.reloading;
  return (
    <section aria-label="AI写作助手" className="ai-writing-assistant">
      <h3>AI写作助手</h3>
      <p>AI只生成候选，不会自动修改正文。生成前会先保存当前正文。</p>
      <label htmlFor="ai-instruction">额外要求（可选）</label>
      <textarea
        id="ai-instruction"
        rows={2}
        maxLength={4000}
        value={instruction}
        onChange={(event) => setInstruction(event.target.value)}
      />
      <button
        type="button"
        disabled={disabled}
        onClick={() => void ai.generate("continue", instruction, null)}
      >
        续写
      </button>
      <button
        type="button"
        disabled={disabled || !selection?.text.trim()}
        onClick={() => void ai.generate("rewrite", instruction, selection)}
      >
        改写选中文本
      </button>
      {ai.status === "generating" ? (
        <p role="status">正在保存并生成候选…</p>
      ) : null}
      {ai.error ? <p role="alert">{ai.error}</p> : null}
      {ai.candidate ? (
        <section aria-label="AI候选">
          <h4>AI候选</h4>
          <textarea
            aria-label="AI候选文本"
            readOnly
            rows={8}
            value={ai.candidate.result.text}
          />
          <p>模型：{ai.candidate.result.model}</p>
          <p>
            上下文来源：
            {ai.candidate.result.context.included_sources.join("、")}；字符数：
            {ai.candidate.result.context.character_count}；
            {ai.candidate.result.context.truncated ? "已按预算截断" : "未截断"}
          </p>
          <button
            type="button"
            disabled={
              writing.state.reloading || writing.state.status === "conflict"
            }
            onClick={ai.adopt}
          >
            {ai.candidate.result.operation === "continue"
              ? "追加到正文"
              : "替换选中文本"}
          </button>
          <button type="button" onClick={ai.discard}>
            丢弃
          </button>
        </section>
      ) : null}
    </section>
  );
}
