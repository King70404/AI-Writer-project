import type { WorkflowCandidate } from "./api/ai-workflow";

/** 作者修改的非空白字符上限，与服务端一致。 */
export const MAX_EDIT_CHARACTERS = 3000;

export function visibleCharacters(text: string): number {
  let total = 0;
  for (const character of text) if (!/\s/u.test(character)) total += 1;
  return total;
}

/** 当前正文版本下能否采用该候选的最新作者修改。 */
export function editIsCurrent(
  candidate: WorkflowCandidate,
  savedRevisionId: string,
): boolean {
  return candidate.latest_edit?.base_revision_id === savedRevisionId;
}
