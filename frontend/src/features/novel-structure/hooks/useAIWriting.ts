import { useEffect, useRef, useState } from "react";
import {
  AIWritingError,
  type AICandidate,
  type AIWritingClient,
  type AIOperation,
} from "../api/ai-writing";
import type { useChapterWriting } from "./useChapterWriting";

export interface SelectionSnapshot {
  readonly start: number;
  readonly end: number;
  readonly text: string;
}
export function appendCandidate(content: string, candidate: string): string {
  return (
    content +
    (content === "" || content.endsWith("\n") ? "" : "\n\n") +
    candidate
  );
}

export function useAIWriting(
  chapterId: string,
  writing: ReturnType<typeof useChapterWriting>,
  client: AIWritingClient,
) {
  const [status, setStatus] = useState<
    "idle" | "generating" | "success" | "error"
  >("idle");
  const [candidate, setCandidate] = useState<{
    result: AICandidate;
    selection: SelectionSnapshot | null;
  } | null>(null);
  const [error, setError] = useState("");
  const busy = useRef(false);
  const request = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      request.current?.abort();
    },
    [],
  );

  const generate = async (
    operation: AIOperation,
    instruction: string,
    selection: SelectionSnapshot | null,
  ) => {
    if (busy.current) return;
    if (operation === "rewrite" && (!selection || !selection.text.trim()))
      return;
    busy.current = true;
    const controller = new AbortController();
    request.current = controller;
    setStatus("generating");
    setError("");
    setCandidate(null);
    try {
      const saved = await writing.flush();
      if (controller.signal.aborted) return;
      if (!saved) throw new AIWritingError("请先保存当前正文后再使用AI。");
      const result =
        operation === "continue"
          ? await client.continueChapter(
              chapterId,
              instruction,
              controller.signal,
            )
          : await client.rewriteChapterText(
              chapterId,
              selection!.text,
              instruction,
              controller.signal,
            );
      if (controller.signal.aborted) return;
      setCandidate({ result, selection });
      setStatus("success");
    } catch (failure) {
      if (controller.signal.aborted) return;
      setError(
        failure instanceof AIWritingError
          ? failure.message
          : "AI请求未能完成，请手动重试。",
      );
      setStatus("error");
    } finally {
      busy.current = false;
    }
  };
  const discard = () => {
    setCandidate(null);
    setError("");
    setStatus("idle");
  };
  const adopt = () => {
    if (
      !candidate ||
      busy.current ||
      writing.state.reloading ||
      writing.state.status === "conflict"
    )
      return;
    const content = writing.getContent();
    const { result, selection } = candidate;
    if (result.operation === "rewrite") {
      if (
        !selection ||
        content.slice(selection.start, selection.end) !== selection.text
      ) {
        setError("原选中文本已发生变化，请重新选择并生成。");
        return;
      }
      writing.edit(
        content.slice(0, selection.start) +
          result.text +
          content.slice(selection.end),
      );
    } else writing.edit(appendCandidate(content, result.text));
    discard();
  };
  return { status, candidate, error, generate, adopt, discard };
}
