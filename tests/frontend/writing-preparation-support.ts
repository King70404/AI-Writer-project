import { vi } from "vitest";
import type { ModelProfile } from "../../frontend/src/features/novel-structure/api/ai-workflow";
import type {
  ChapterPlan,
  RuleRevision,
  WritingPreparationClient,
  WritingReference,
} from "../../frontend/src/features/novel-structure/api/writing-preparation";
import {
  chapterId,
  structureProjectId,
  structureTimestamp,
} from "./novel-structure-support";

export const studyModel: ModelProfile = {
  id: "study-model",
  name: "分析模型",
  kind: "cloud",
  base_url: "https://model.example/v1",
  model: "study",
  max_output_tokens: 8192,
  has_key: true,
};
export const studyRule = {
  name: "动作承接",
  instruction: "重要动作应连接姿态、行动和后果。",
  applies_to: "冲突场景；过场不必放慢。",
};
export function ruleRevision(
  overrides: Partial<RuleRevision> = {},
): RuleRevision {
  return {
    id: "rules-version-one",
    rule_id: "rules-one",
    project_id: structureProjectId,
    version: 1,
    title: "动作方法",
    reference_id: "reference-one",
    rules: [studyRule],
    created_at: structureTimestamp,
    ...overrides,
  };
}
export function writingReference(
  overrides: Partial<WritingReference> = {},
): WritingReference {
  return {
    id: "reference-one",
    project_id: structureProjectId,
    title: "庭院范文",
    text: "😀风吹门响。她停住脚。",
    granularity: "sentence",
    units: [
      { id: "u1", start: 0, end: 6, text: "😀风吹门响。" },
      { id: "u2", start: 6, end: 11, text: "她停住脚。" },
    ],
    model_snapshot: studyModel,
    messages: [
      { role: "system", content: "区分效果与推测意图。" },
      { role: "user", content: "😀风吹门响。她停住脚。" },
    ],
    status: "ready",
    version: 1,
    attempts: 0,
    last_error: null,
    analysis: null,
    created_at: structureTimestamp,
    ...overrides,
  };
}
export function analyzedReference(
  overrides: Partial<WritingReference> = {},
): WritingReference {
  return writingReference({
    status: "analyzed",
    attempts: 1,
    version: 3,
    analysis: {
      units: [
        {
          unit_id: "u1",
          quote: "门响",
          function: "环境触发",
          effect: "让停顿有因",
          rationale: "可能用于制造警觉",
          transfer: "用具体感官引出行动",
        },
        {
          unit_id: "u2",
          quote: "停住脚",
          function: "动作反应",
          effect: "延迟信息",
          rationale: "可能在等待辨认",
          transfer: "先反应再解释",
        },
      ],
      long_form_notes: "每章保持一至三个重点，并在后文承接动作后果。",
      rules: [studyRule],
    },
    ...overrides,
  });
}
export function chapterPlan(overrides: Partial<ChapterPlan> = {}): ChapterPlan {
  return {
    chapter_id: chapterId,
    project_id: structureProjectId,
    version: 1,
    revision_id: "planning-one",
    updated_at: structureTimestamp,
    memory_focuses: ["主人公开始怀疑来客"],
    target_characters: 3000,
    chapter_goal: "从信任到试探",
    conflict: "来客隐藏动机",
    continuity_notes: "承接上一章来客的承诺",
    scenes: [],
    include_story_bible: true,
    writing_rule_revision_ids: ["rules-version-one"],
    ...overrides,
  };
}
export function preparationClient(
  overrides: Partial<WritingPreparationClient> = {},
): WritingPreparationClient {
  return {
    references: vi.fn().mockResolvedValue([]),
    reference: vi.fn().mockResolvedValue(writingReference()),
    prepareReference: vi.fn().mockResolvedValue(writingReference()),
    analyze: vi.fn().mockResolvedValue(analyzedReference()),
    rules: vi.fn().mockResolvedValue([]),
    confirmRules: vi.fn().mockResolvedValue(ruleRevision()),
    plan: vi.fn().mockResolvedValue(null),
    savePlan: vi.fn().mockResolvedValue(chapterPlan()),
    ...overrides,
  };
}
