import { expectCleanBrowserAudit } from "../support/assertions";
import { expect, test } from "../support/fixture";

const concurrentCandidates = [
  {
    title: "E2E-STORY-BIBLE-TITLE-CANARY-011-A",
    content: "E2E-STORY-BIBLE-CONTENT-CANARY-011-A",
  },
  {
    title: "E2E-STORY-BIBLE-TITLE-CANARY-011-B",
    content: "E2E-STORY-BIBLE-CONTENT-CANARY-011-B",
  },
] as const;

test("E2E-INT-011 exercises the Story Bible HTTP chain independently of its UI", async ({
  baseURL,
  browserAudit,
  context,
  page,
}) => {
  expect(baseURL).toBeDefined();
  const origin = new URL(baseURL ?? "http://invalid").origin;
  expect(origin).toBe(browserAudit.allowedOrigin);

  browserAudit.allowOneExpectedSessionCookie();
  const session = await context.request.get("/api/v1/security/session", {
    headers: { Origin: origin },
  });
  expect(session.status()).toBe(200);
  const sessionBody = (await session.json()) as { readonly csrf_token: string };
  const writeHeaders = {
    Origin: origin,
    "X-CSRF-Token": sessionBody.csrf_token,
  };

  const project = await context.request.post("/api/v1/projects", {
    data: { title: "Story Bible E2E owner", description: "Unchanged" },
    headers: writeHeaders,
  });
  expect(project.status()).toBe(201);
  const projectBody = (await project.json()) as { readonly project_id: string };

  const created = await context.request.post(
    `/api/v1/projects/${projectBody.project_id}/story-bible`,
    {
      data: { title: " Initial Story Bible ", content: "Line A\r\nLine B" },
      headers: writeHeaders,
    },
  );
  expect(created.status()).toBe(201);
  expect(created.headers().etag).toBe('"1"');
  expect(created.headers().location).toMatch(
    /^\/api\/v1\/story-bibles\/sbl_[0-9A-HJKMNP-TV-Z]{26}$/,
  );
  expect(created.headers()["cache-control"]).toBe("no-store");
  const createdBody = (await created.json()) as {
    readonly story_bible_id: string;
    readonly current_revision_id: string;
    readonly revision_number: number;
    readonly concurrency_version: number;
    readonly title: string;
    readonly content: string;
  };
  expect(createdBody.title).toBe("Initial Story Bible");
  expect(createdBody.content).toBe("Line A\nLine B");
  expect(createdBody.revision_number).toBe(1);
  expect(createdBody.concurrency_version).toBe(1);

  const sessionResponsesBeforeReads = browserAudit.responses.filter(
    (response) => response.path === "/api/v1/security/session",
  ).length;
  const nested = await context.request.get(
    `/api/v1/projects/${projectBody.project_id}/story-bible`,
  );
  const directPath = `/api/v1/story-bibles/${createdBody.story_bible_id}`;
  const direct = await context.request.get(directPath);
  expect(nested.status()).toBe(200);
  expect(direct.status()).toBe(200);
  expect(await nested.json()).toEqual(await direct.json());
  expect(nested.headers().etag).toBe('"1"');
  expect(direct.headers().etag).toBe('"1"');
  expect(
    browserAudit.responses.filter(
      (response) => response.path === "/api/v1/security/session",
    ),
  ).toHaveLength(sessionResponsesBeforeReads);

  const revised = await context.request.put(directPath, {
    data: { title: "Replacement Story Bible", content: "" },
    headers: { ...writeHeaders, "If-Match": '"1"' },
  });
  expect(revised.status()).toBe(200);
  expect(revised.headers().etag).toBe('"2"');
  const revisedBody = (await revised.json()) as {
    readonly revision_number: number;
    readonly concurrency_version: number;
    readonly title: string;
    readonly content: string;
  };
  expect(revisedBody.revision_number).toBe(2);
  expect(revisedBody.concurrency_version).toBe(2);
  expect(revisedBody.title).toBe("Replacement Story Bible");
  expect(revisedBody.content).toBe("");

  const concurrent = await Promise.all(
    concurrentCandidates.map((candidate) =>
      context.request.put(directPath, {
        data: candidate,
        headers: { ...writeHeaders, "If-Match": '"2"' },
      }),
    ),
  );
  expect(concurrent.map((response) => response.status()).sort()).toEqual([
    200, 412,
  ]);
  const winner = concurrent.find((response) => response.status() === 200);
  const loser = concurrent.find((response) => response.status() === 412);
  expect(winner).toBeDefined();
  expect(loser).toBeDefined();
  expect(winner?.headers().etag).toBe('"3"');
  const winnerBody = (await winner?.json()) as {
    readonly revision_number: number;
    readonly concurrency_version: number;
    readonly title: string;
    readonly content: string;
  };
  expect(winnerBody.revision_number).toBe(3);
  expect(winnerBody.concurrency_version).toBe(3);
  expect(concurrentCandidates).toContainEqual({
    title: winnerBody.title,
    content: winnerBody.content,
  });
  const staleBody = (await loser?.json()) as {
    readonly error: {
      readonly code: string;
      readonly details: {
        readonly expected_version: number;
        readonly actual_version: number;
      };
    };
  };
  expect(staleBody.error.code).toBe("STORY_BIBLE_VERSION_CONFLICT");
  expect(staleBody.error.details).toEqual({
    expected_version: 2,
    actual_version: 3,
  });
  for (const candidate of concurrentCandidates) {
    expect(JSON.stringify(staleBody)).not.toContain(candidate.title);
    expect(JSON.stringify(staleBody)).not.toContain(candidate.content);
  }

  const persisted = await context.request.get(directPath);
  expect(persisted.status()).toBe(200);
  expect(persisted.headers().etag).toBe('"3"');
  expect(await persisted.json()).toMatchObject(winnerBody);

  const forbiddenWrite = await context.request.put(directPath, {
    data: { title: "No session", content: "" },
    headers: { Origin: origin, "If-Match": '"3"' },
  });
  expect(forbiddenWrite.status()).toBe(403);
  const forbiddenBody = (await forbiddenWrite.json()) as {
    readonly error: { readonly code: string };
  };
  expect(forbiddenBody.error.code).toBe("CSRF_TOKEN_REQUIRED");

  expect(
    (
      await context.request.patch(directPath, {
        data: { title: "No patch", content: "" },
        headers: { ...writeHeaders, "If-Match": '"3"' },
      })
    ).status(),
  ).toBe(405);
  expect(
    (
      await context.request.delete(directPath, {
        headers: { ...writeHeaders, "If-Match": '"3"' },
      })
    ).status(),
  ).toBe(405);
  const immutableHistory = await context.request.get(`${directPath}/revisions`);
  expect(immutableHistory.status()).toBe(200);
  const immutableHistoryBody = (await immutableHistory.json()) as {
    readonly items: readonly Readonly<Record<string, unknown>>[];
  };
  expect(
    immutableHistoryBody.items.map((item) => item.revision_number),
  ).toEqual([3, 2, 1]);
  expect(
    immutableHistoryBody.items.every((item) => !Object.hasOwn(item, "content")),
  ).toBe(true);
  expect(
    (await context.request.get("/api/v1/story-bibles/not-a-route")).status(),
  ).toBe(422);

  const projectPage = await page.goto(`/projects/${projectBody.project_id}`);
  expect(projectPage?.status()).toBe(200);
  await expect(page.getByRole("link", { name: "小说设定" })).toHaveAttribute(
    "href",
    `/projects/${projectBody.project_id}/story-bible`,
  );
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
  expect(await page.evaluate(() => sessionStorage.length)).toBe(0);
  expect(
    await page.evaluate(
      () => `${JSON.stringify(localStorage)}${JSON.stringify(sessionStorage)}`,
    ),
  ).not.toMatch(/csrf|token|etag|story.?bible|content/iu);

  const unknownFrontend = await page.goto(
    `/story-bibles/${createdBody.story_bible_id}`,
  );
  expect(unknownFrontend?.status()).toBe(200);
  await expect(page.getByRole("heading", { name: "页面不存在" })).toBeVisible();
  expectCleanBrowserAudit(browserAudit);
});
