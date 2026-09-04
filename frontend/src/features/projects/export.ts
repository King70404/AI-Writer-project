import { getText } from "../../api/client";
import { isCanonicalProjectId } from "./api/parsers";

export function exportProjectManuscript(projectId: string): Promise<string> {
  if (!isCanonicalProjectId(projectId)) {
    throw new Error("项目编号无效。");
  }
  return getText(`/projects/${projectId}/export.txt`);
}

export function manuscriptFilename(title: string): string {
  const safe = Array.from(title, (character) =>
    character.charCodeAt(0) < 32 || /[<>:"/\\|?*\u007f]/u.test(character)
      ? "_"
      : character,
  )
    .join("")
    .trim();
  return `${safe || "novel"}.txt`;
}

export function downloadManuscript(text: string, title: string): void {
  const url = URL.createObjectURL(
    new Blob([text], { type: "text/plain;charset=utf-8" }),
  );
  const anchor = document.createElement("a");
  try {
    anchor.href = url;
    anchor.download = manuscriptFilename(title);
    document.body.append(anchor);
    anchor.click();
  } finally {
    anchor.remove();
    URL.revokeObjectURL(url);
  }
}
