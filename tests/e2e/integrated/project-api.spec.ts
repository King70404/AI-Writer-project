import { expectCleanBrowserAudit } from "../support/assertions";
import { expect, test } from "../support/fixture";

const titleCanary = "E2E-PROJECT-TITLE-CANARY-006";
const descriptionCanary = "E2E-PROJECT-DESCRIPTION-CANARY-006";

test("E2E-INT-006 exercises the complete Project API chain without a Project UI", async ({
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

  const created = await context.request.post("/api/v1/projects", {
    data: { title: titleCanary, description: descriptionCanary },
    headers: writeHeaders,
  });
  expect(created.status()).toBe(201);
  expect(created.headers().etag).toBe('"1"');
  expect(created.headers().location).toMatch(
    /^\/api\/v1\/projects\/prj_[0-9A-HJKMNP-TV-Z]{26}$/,
  );
  expect(created.headers()["cache-control"]).toBe("no-store");
  expect(created.headers()["x-request-id"]).toBeTruthy();
  const createdBody = (await created.json()) as {
    readonly project_id: string;
    readonly current_revision_id: string;
    readonly revision_number: number;
    readonly concurrency_version: number;
  };
  expect(createdBody.revision_number).toBe(1);
  expect(createdBody.concurrency_version).toBe(1);

  const projectPath = `/api/v1/projects/${createdBody.project_id}`;
  const current = await context.request.get(projectPath);
  expect(current.status()).toBe(200);
  expect(current.headers().etag).toBe('"1"');
  const currentBody = (await current.json()) as {
    readonly current_revision_id: string;
  };
  expect(currentBody.current_revision_id).toBe(createdBody.current_revision_id);

  const revised = await context.request.put(projectPath, {
    data: { title: "Revised Project", description: "Complete replacement" },
    headers: { ...writeHeaders, "If-Match": '"1"' },
  });
  expect(revised.status()).toBe(200);
  expect(revised.headers().etag).toBe('"2"');
  const revisedBody = (await revised.json()) as {
    readonly revision_number: number;
    readonly concurrency_version: number;
  };
  expect(revisedBody.revision_number).toBe(2);
  expect(revisedBody.concurrency_version).toBe(2);

  const stale = await context.request.put(projectPath, {
    data: { title: titleCanary, description: descriptionCanary },
    headers: { ...writeHeaders, "If-Match": '"1"' },
  });
  expect(stale.status()).toBe(412);
  const staleBody = (await stale.json()) as {
    readonly error: { readonly code: string };
  };
  expect(staleBody.error.code).toBe("PROJECT_VERSION_CONFLICT");
  expect(JSON.stringify(staleBody)).not.toContain(titleCanary);
  expect(JSON.stringify(staleBody)).not.toContain(descriptionCanary);

  const invalidHost = await context.request.get(projectPath, {
    headers: { Host: "external.invalid" },
  });
  expect(invalidHost.status()).toBe(400);
  const invalidHostBody = (await invalidHost.json()) as {
    readonly error: { readonly code: string };
  };
  expect(invalidHostBody.error.code).toBe("INVALID_HOST");
  expect((await context.request.get("/openapi.json")).status()).toBe(404);
  expect((await context.request.get("/docs")).status()).toBe(404);

  const pageResponse = await page.goto("/not-a-real-route");
  expect(pageResponse?.status()).toBe(200);
  await expect(page.getByRole("heading", { name: "页面不存在" })).toBeVisible();
  expectCleanBrowserAudit(browserAudit);
});
