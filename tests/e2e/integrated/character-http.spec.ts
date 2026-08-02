import { expectCleanBrowserAudit } from "../support/assertions";
import { expect, test } from "../support/fixture";

interface CharacterRevisionHistoryItemBody {
  readonly revision_id: string;
  readonly revision_number: number;
  readonly name: string;
  readonly role: string;
  readonly created_at: string;
  readonly is_current: boolean;
}

interface CharacterRevisionHistoryPageBody {
  readonly character_id: string;
  readonly project_id: string;
  readonly current_revision_number: number;
  readonly items: readonly CharacterRevisionHistoryItemBody[];
  readonly next_cursor: string | null;
  readonly has_more: boolean;
}

interface CharacterRevisionBody {
  readonly character_id: string;
  readonly project_id: string;
  readonly revision_id: string;
  readonly revision_number: number;
  readonly name: string;
  readonly role: string;
  readonly profile: string;
  readonly created_at: string;
  readonly is_current: boolean;
  readonly current_revision_number: number;
}

test("E2E-INT-014 exercises Character HTTP creation, stable listing, and concurrent revision", async ({
  baseURL,
  browserAudit,
  context,
  page,
  playwright,
}) => {
  expect(baseURL).toBeDefined();
  const origin = new URL(baseURL ?? "http://invalid").origin;
  expect(origin).toBe(browserAudit.allowedOrigin);

  browserAudit.allowOneExpectedSessionCookie();
  const session = await context.request.get("/api/v1/security/session", {
    headers: { Origin: origin },
  });
  expect(session.status()).toBe(200);
  const csrf = ((await session.json()) as { readonly csrf_token: string })
    .csrf_token;
  const writeHeaders = { Origin: origin, "X-CSRF-Token": csrf };
  const project = await context.request.post("/api/v1/projects", {
    data: { title: "Character HTTP E2E owner", description: "Unchanged" },
    headers: writeHeaders,
  });
  expect(project.status()).toBe(201);
  const projectId = ((await project.json()) as { readonly project_id: string })
    .project_id;

  const first = await context.request.post(
    `/api/v1/projects/${projectId}/characters`,
    {
      data: {
        name: "Shared Character",
        role: "Lead",
        profile: "E2E-CHARACTER-PROFILE-CANARY-014-A",
      },
      headers: writeHeaders,
    },
  );
  expect(first.status()).toBe(201);
  expect(first.headers().etag).toBe('"1"');
  expect(first.headers().location).toMatch(
    /^\/api\/v1\/characters\/chr_[0-9A-HJKMNP-TV-Z]{26}$/,
  );
  const firstBody = (await first.json()) as {
    readonly character_id: string;
    readonly concurrency_version: number;
    readonly revision_number: number;
    readonly profile: string;
  };
  expect(firstBody.concurrency_version).toBe(1);
  expect(firstBody.revision_number).toBe(1);

  const second = await context.request.post(
    `/api/v1/projects/${projectId}/characters`,
    {
      data: {
        name: "Shared Character",
        role: "Rival",
        profile: "E2E-CHARACTER-PROFILE-CANARY-014-B",
      },
      headers: writeHeaders,
    },
  );
  expect(second.status()).toBe(201);
  const secondBody = (await second.json()) as {
    readonly character_id: string;
  };
  expect(secondBody.character_id).not.toBe(firstBody.character_id);

  const listed = await context.request.get(
    `/api/v1/projects/${projectId}/characters`,
  );
  expect(listed.status()).toBe(200);
  const listedBody = (await listed.json()) as {
    readonly items: readonly Readonly<Record<string, unknown>>[];
    readonly has_more: boolean;
  };
  expect(listedBody.items).toHaveLength(2);
  expect(
    listedBody.items.every((item) => !Object.hasOwn(item, "profile")),
  ).toBe(true);
  expect(listedBody.has_more).toBe(false);

  const firstPath = `/api/v1/characters/${firstBody.character_id}`;
  const complete = await context.request.get(firstPath);
  expect(complete.status()).toBe(200);
  const completeBody = (await complete.json()) as { readonly profile: string };
  expect(completeBody.profile).toBe("E2E-CHARACTER-PROFILE-CANARY-014-A");
  const revised = await context.request.put(firstPath, {
    data: {
      name: "Revised Character",
      role: "",
      profile: "E2E-CHARACTER-PROFILE-CANARY-014-REVISION-2",
    },
    headers: { ...writeHeaders, "If-Match": '"1"' },
  });
  expect(revised.status()).toBe(200);
  expect(revised.headers().etag).toBe('"2"');

  const independent = await Promise.all(
    [0, 1].map(async (index) => {
      const request = await playwright.request.newContext({ baseURL });
      const security = await request.get("/api/v1/security/session", {
        headers: { Origin: origin },
      });
      const token = ((await security.json()) as { readonly csrf_token: string })
        .csrf_token;
      return { index, request, token };
    }),
  );
  const concurrent = await Promise.all(
    independent.map(({ index, request, token }) =>
      request.put(firstPath, {
        data: {
          name: `Concurrent Character ${index}`,
          role: `Role ${index}`,
          profile: `E2E-CHARACTER-PROFILE-CANARY-014-CONCURRENT-${index}`,
        },
        headers: {
          Origin: origin,
          "X-CSRF-Token": token,
          "If-Match": '"2"',
        },
      }),
    ),
  );
  expect(concurrent.map((response) => response.status()).sort()).toEqual([
    200, 412,
  ]);
  const winner = concurrent.find((response) => response.status() === 200);
  const conflict = concurrent.find((response) => response.status() === 412);
  expect(winner?.headers().etag).toBe('"3"');
  const conflictBody = (await conflict?.json()) as {
    readonly error: Readonly<Record<string, unknown>>;
  };
  expect(conflictBody.error).toMatchObject({
    code: "CHARACTER_VERSION_CONFLICT",
    details: { expected_version: 2, actual_version: 3 },
  });
  await Promise.all(independent.map(({ request }) => request.dispose()));

  const sibling = await context.request.get(
    `/api/v1/characters/${secondBody.character_id}`,
  );
  expect(sibling.status()).toBe(200);
  expect(sibling.headers().etag).toBe('"1"');
  const siblingBody = (await sibling.json()) as { readonly profile: string };
  expect(siblingBody.profile).toBe("E2E-CHARACTER-PROFILE-CANARY-014-B");
  expect(
    (
      await context.request.patch(firstPath, {
        data: {},
        headers: { ...writeHeaders, "If-Match": '"3"' },
      })
    ).status(),
  ).toBe(405);
  expect(
    (
      await context.request.delete(firstPath, {
        headers: { ...writeHeaders, "If-Match": '"3"' },
      })
    ).status(),
  ).toBe(405);

  const historyRequest = await playwright.request.newContext({ baseURL });
  try {
    const currentBeforeHistory = await historyRequest.get(firstPath);
    expect(currentBeforeHistory.status()).toBe(200);
    const currentBeforeHistoryBody = (await currentBeforeHistory.json()) as {
      readonly current_revision_id: string;
      readonly revision_number: number;
    };
    expect(currentBeforeHistoryBody.revision_number).toBe(3);

    const historyBefore = await historyRequest.get(`${firstPath}/revisions`);
    expect(historyBefore.status()).toBe(200);
    expect(historyBefore.headers()["cache-control"]).toBe("no-store");
    expect(historyBefore.headers().etag).toBeUndefined();
    const historyBeforeBody =
      (await historyBefore.json()) as CharacterRevisionHistoryPageBody;
    expect(historyBeforeBody.character_id).toBe(firstBody.character_id);
    expect(historyBeforeBody.project_id).toBe(projectId);
    expect(historyBeforeBody.current_revision_number).toBe(3);
    expect(historyBeforeBody.items.map((item) => item.revision_number)).toEqual(
      [3, 2, 1],
    );
    expect(
      historyBeforeBody.items.every(
        (item) => item.is_current === (item.revision_number === 3),
      ),
    ).toBe(true);
    expect(
      historyBeforeBody.items.every((item) => !Object.hasOwn(item, "profile")),
    ).toBe(true);
    expect(historyBeforeBody.has_more).toBe(false);
    expect(historyBeforeBody.next_cursor).toBeNull();
    expect(Object.hasOwn(historyBeforeBody, "etag")).toBe(false);

    const revisionOne = await historyRequest.get(`${firstPath}/revisions/1`);
    expect(revisionOne.status()).toBe(200);
    expect(revisionOne.headers()["cache-control"]).toBe("no-store");
    expect(revisionOne.headers().etag).toBeUndefined();
    const revisionOneBody = (await revisionOne.json()) as CharacterRevisionBody;
    expect(revisionOneBody).toMatchObject({
      character_id: firstBody.character_id,
      project_id: projectId,
      revision_number: 1,
      name: "Shared Character",
      role: "Lead",
      profile: "E2E-CHARACTER-PROFILE-CANARY-014-A",
      is_current: false,
      current_revision_number: 3,
    });
    expect(revisionOneBody.revision_id).toMatch(
      /^crv_[0-9A-HJKMNP-TV-Z]{26}$/u,
    );
    expect(Object.hasOwn(revisionOneBody, "etag")).toBe(false);

    const forbiddenHistoryWrites = [
      await context.request.post(`${firstPath}/revisions`, {
        data: {},
        headers: writeHeaders,
      }),
      await context.request.put(`${firstPath}/revisions/1`, {
        data: {},
        headers: writeHeaders,
      }),
      await context.request.patch(`${firstPath}/revisions/1`, {
        data: {},
        headers: writeHeaders,
      }),
      await context.request.delete(`${firstPath}/revisions/1`, {
        headers: writeHeaders,
      }),
    ];
    expect(forbiddenHistoryWrites.map((response) => response.status())).toEqual(
      [405, 405, 405, 405],
    );
    const forbiddenLifecycleWrites = [
      await context.request.post(`${firstPath}/rollback`, {
        data: {},
        headers: writeHeaders,
      }),
      await context.request.post(`${firstPath}/restore`, {
        data: {},
        headers: writeHeaders,
      }),
    ];
    expect(
      forbiddenLifecycleWrites.map((response) => response.status()),
    ).toEqual([405, 405]);
    for (const response of [
      ...forbiddenHistoryWrites,
      ...forbiddenLifecycleWrites,
    ]) {
      expect(await response.text()).not.toMatch(
        /E2E-CHARACTER-PROFILE|sqlite|no such table|traceback|csrf|session|if-match|[A-Z]:\\/iu,
      );
    }

    const historyAfter = await historyRequest.get(`${firstPath}/revisions`);
    expect(historyAfter.status()).toBe(200);
    const historyAfterBody =
      (await historyAfter.json()) as CharacterRevisionHistoryPageBody;
    expect(historyAfterBody.items).toHaveLength(historyBeforeBody.items.length);
    expect(
      historyAfterBody.items.map((item) => [
        item.revision_id,
        item.revision_number,
        item.is_current,
      ]),
    ).toEqual(
      historyBeforeBody.items.map((item) => [
        item.revision_id,
        item.revision_number,
        item.is_current,
      ]),
    );
    expect(historyAfterBody.current_revision_number).toBe(
      historyBeforeBody.current_revision_number,
    );

    const currentAfterHistory = await historyRequest.get(firstPath);
    expect(currentAfterHistory.status()).toBe(200);
    const currentAfterHistoryBody = (await currentAfterHistory.json()) as {
      readonly current_revision_id: string;
      readonly revision_number: number;
    };
    expect(currentAfterHistoryBody).toEqual(currentBeforeHistoryBody);
  } finally {
    await historyRequest.dispose();
  }

  expect(
    (
      await context.request.get(
        `/api/v1/characters/${firstBody.character_id}/relationships`,
      )
    ).status(),
  ).toBe(404);

  const unknownFrontend = await page.goto(
    `/characters/${firstBody.character_id}`,
  );
  expect(unknownFrontend?.status()).toBe(200);
  await expect(page.getByRole("heading", { name: "页面不存在" })).toBeVisible();
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
  expect(await page.evaluate(() => sessionStorage.length)).toBe(0);
  expect(
    await page.evaluate(
      () => `${JSON.stringify(localStorage)}${JSON.stringify(sessionStorage)}`,
    ),
  ).not.toMatch(/csrf|etag|cursor|profile/iu);
  expectCleanBrowserAudit(browserAudit);
});
