import { useRef, useState } from "react";

import { ApiError } from "../../../api/errors";
import { downloadManuscript, exportProjectManuscript } from "../export";

export function ExportManuscriptButton({
  projectId,
  title,
}: {
  readonly projectId: string;
  readonly title: string;
}) {
  const pending = useRef(false);
  const [state, setState] = useState<"idle" | "exporting" | "error">("idle");
  const [message, setMessage] = useState("");
  async function exportNovel() {
    if (pending.current) return;
    pending.current = true;
    setState("exporting");
    setMessage("");
    try {
      const text = await exportProjectManuscript(projectId);
      downloadManuscript(text, title);
      setState("idle");
    } catch (error) {
      setMessage(
        error instanceof ApiError && error.status === 404
          ? "项目不存在，无法导出小说。"
          : "导出失败，请检查连接后重试。",
      );
      setState("error");
    } finally {
      pending.current = false;
    }
  }
  return (
    <div>
      <button
        type="button"
        disabled={state === "exporting"}
        onClick={() => void exportNovel()}
      >
        {state === "exporting" ? "正在导出…" : "导出小说"}
      </button>
      <p>导出服务器当前已保存正文。</p>
      {state === "error" ? <p role="alert">{message}</p> : null}
    </div>
  );
}
