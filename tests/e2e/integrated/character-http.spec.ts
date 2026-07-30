import { expectCleanBrowserAudit } from "../support/assertions";
import { expect, test } from "../support/fixture";

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
  expect((await context.request.get(`${firstPath}/revisions`)).status()).toBe(
    404,
  );
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
