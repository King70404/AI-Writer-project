import { afterEach, expect, it, vi } from "vitest";
import { ApiError } from "../../frontend/src/api/errors";
import { securitySession } from "../../frontend/src/api/security-session";
import {
  analysisFailureMessage,
  parseChapterPlan,
  parseRuleRevision,
  parseWritingReference,
  preparationError,
  writingPreparationClient,
} from "../../frontend/src/features/novel-structure/api/writing-preparation";
import { chapterId, structureProjectId } from "./novel-structure-support";
import {
  analyzedReference,
  chapterPlan,
  ruleRevision,
  writingReference,
} from "./writing-preparation-support";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  securitySession.clear();
});

it("decodes Unicode codepoint ranges and genuine substring evidence without demanding an entire sentence", () => {
  const result = parseWritingReference(analyzedReference(), structureProjectId);
  expect(result.units[1].text).toBe("她停住脚。");
  expect(result.analysis?.units[0].quote).toBe("门响");
  expect(result.model_snapshot.has_key).toBe(false);
});

it.each([
  { project_id: "another-project" },
  { granularity: ["sentence"] },
  { status: ["ready"] },
  { attempts: 4 },
  { units: [] },
  { units: [writingReference().units[0], writingReference().units[0]] },
  { units: [{ ...writingReference().units[0], end: 7 }] },
  { messages: [{ role: "assistant", content: "x" }] },
  {
    model_snapshot: {
      ...writingReference().model_snapshot,
      api_key: "fake",
    },
  },
  { status: "analyzed" },
])("rejects untrusted or inconsistent reference metadata %j", (patch) => {
  expect(() =>
    parseWritingReference(
      { ...writingReference(), ...patch },
      structureProjectId,
    ),
  ).toThrow("无法安全读取");
});

it.each([
  { quote: "不存在的引文" },
  { quote: " " },
  { unit_id: "unknown" },
  { effect: null },
])("rejects fabricated or broken analysis evidence %j", (patch) => {
  const reference = analyzedReference();
  expect(() =>
    parseWritingReference(
      {
        ...reference,
        analysis: {
          ...reference.analysis,
          units: [
            { ...reference.analysis!.units[0], ...patch },
            reference.analysis!.units[1],
          ],
        },
      },
      structureProjectId,
    ),
  ).toThrow("无法安全读取");
});

it("rejects omitted and duplicate analysis units", () => {
  const reference = analyzedReference();
  for (const units of [
    [reference.analysis!.units[0]],
    [reference.analysis!.units[0], reference.analysis!.units[0]],
  ]) {
    expect(() =>
      parseWritingReference(
        { ...reference, analysis: { ...reference.analysis, units } },
        structureProjectId,
      ),
    ).toThrow();
  }
});

it("only accepts plans and rule versions belonging to the requested resources", () => {
  expect(parseChapterPlan(null, structureProjectId, chapterId)).toBeNull();
  expect(
    parseChapterPlan(chapterPlan(), structureProjectId, chapterId),
  ).toEqual(chapterPlan());
  expect(parseRuleRevision(ruleRevision(), structureProjectId)).toEqual(
    ruleRevision(),
  );
  expect(() => parseChapterPlan(chapterPlan(), "other", chapterId)).toThrow();
  expect(() =>
    parseChapterPlan(chapterPlan(), structureProjectId, "other"),
  ).toThrow();
  expect(() =>
    parseChapterPlan(
      chapterPlan({ target_characters: 20001 }),
      structureProjectId,
      chapterId,
    ),
  ).toThrow();
  expect(() => parseRuleRevision(ruleRevision(), "other")).toThrow();
  expect(() =>
    parseRuleRevision(
      { ...ruleRevision(), rules: [{ name: "bad" }] },
      structureProjectId,
    ),
  ).toThrow();
});

it("uses CSRF proof, immutable rule IDs and expected versions for explicit mutations", async () => {
  vi.spyOn(securitySession, "getValidSession").mockResolvedValue({
    csrfToken: "test-proof",
    expiresAtMilliseconds: Date.now() + 60000,
  });
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(Response.json(writingReference()))
    .mockResolvedValueOnce(Response.json(analyzedReference()))
    .mockResolvedValueOnce(Response.json(ruleRevision()))
    .mockResolvedValueOnce(
      Response.json(ruleRevision({ id: "rules-two", version: 2 })),
    )
    .mockResolvedValueOnce(Response.json(chapterPlan()));
  vi.stubGlobal("fetch", fetcher);
  const input = {
    title: "庭院",
    text: writingReference().text,
    granularity: "sentence" as const,
    profile_id: "study-model",
  };
  await writingPreparationClient.prepareReference(structureProjectId, input);
  await writingPreparationClient.analyze(
    structureProjectId,
    writingReference(),
    true,
  );
  const rule = ruleRevision();
  const ruleInput = {
    title: rule.title,
    reference_id: rule.reference_id,
    rules: rule.rules,
  };
  await writingPreparationClient.confirmRules(structureProjectId, ruleInput);
  await writingPreparationClient.confirmRules(
    structureProjectId,
    ruleInput,
    rule,
  );
  const plan = chapterPlan();
  await writingPreparationClient.savePlan(
    structureProjectId,
    chapterId,
    {
      memory_focuses: plan.memory_focuses,
      target_characters: plan.target_characters,
      chapter_goal: plan.chapter_goal,
      conflict: plan.conflict,
      continuity_notes: plan.continuity_notes,
      scenes: plan.scenes,
      include_story_bible: plan.include_story_bible,
      writing_rule_revision_ids: plan.writing_rule_revision_ids,
    },
    1,
  );
  expect(fetcher).toHaveBeenCalledTimes(5);
  const options = fetcher.mock.calls.map((call) => call[1] as RequestInit);
  expect(
    options.every(
      (item) =>
        new Headers(item.headers).get("X-CSRF-Token") === "test-proof" &&
        item.credentials === "same-origin",
    ),
  ).toBe(true);
  expect(JSON.parse(options[1].body as string)).toEqual({
    expected_version: 1,
    cloud_consent: true,
  });
  expect(fetcher.mock.calls[3][0]).toContain("/rules/rules-one/versions");
  expect(JSON.parse(options[3].body as string)).toEqual({
    ...ruleInput,
    expected_version: 1,
    confirmed: true,
  });
  expect(options[4].method).toBe("PUT");
  expect(JSON.parse(options[4].body as string)).toMatchObject({
    expected_version: 1,
    writing_rule_revision_ids: [rule.id],
  });
});

it("reads persisted references, plans and rules without issuing model calls", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(Response.json([analyzedReference()]))
    .mockResolvedValueOnce(Response.json(analyzedReference()))
    .mockResolvedValueOnce(Response.json([ruleRevision()]))
    .mockResolvedValueOnce(Response.json(chapterPlan()));
  vi.stubGlobal("fetch", fetcher);
  expect(
    await writingPreparationClient.references(structureProjectId),
  ).toHaveLength(1);
  expect(
    (
      await writingPreparationClient.reference(
        structureProjectId,
        "reference-one",
      )
    ).status,
  ).toBe("analyzed");
  expect(await writingPreparationClient.rules(structureProjectId)).toHaveLength(
    1,
  );
  expect(
    (await writingPreparationClient.plan(structureProjectId, chapterId))
      ?.version,
  ).toBe(1);
  expect(
    fetcher.mock.calls.every(
      (call) => (call[1] as RequestInit).method === "GET",
    ),
  ).toBe(true);
});

it("does not resend failed requests or render provider secrets", async () => {
  const fetcher = vi
    .fn()
    .mockRejectedValue(new Error("private transport body"));
  vi.stubGlobal("fetch", fetcher);
  await expect(
    writingPreparationClient.references(structureProjectId),
  ).rejects.toThrow("不会自动重发");
  expect(fetcher).toHaveBeenCalledOnce();
  const error = new ApiError({
    code: "PLANNING_CONFLICT",
    status: 409,
    message: "private text",
    details: {},
    retryable: false,
    suggestedAction: null,
    requestId: null,
  });
  expect(preparationError(error).message).toContain("草稿已保留");
  expect(analysisFailureMessage("WritingOutputInvalid")).toContain(
    "引文与原文不符",
  );
  expect(analysisFailureMessage("WritingInterrupted")).toContain("中断");
  expect(analysisFailureMessage("AIProviderRateLimited")).toContain(
    "请求过于频繁",
  );
  expect(analysisFailureMessage("secret provider body")).not.toContain(
    "secret",
  );
  const clear = vi.spyOn(securitySession, "clear");
  preparationError(new ApiError({ ...error, code: "AUTH", status: 401 }));
  expect(clear).toHaveBeenCalledOnce();
});
