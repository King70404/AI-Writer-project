import {
  expectCleanBrowserAudit,
  expectSecurityHeaders,
} from "../support/assertions";
import { expect, test } from "../support/fixture";

interface ProjectListItem {
  readonly project_id: string;
  readonly current_revision_id: string;
  readonly revision_number: number;
  readonly concurrency_version: number;
  readonly title: string;
  readonly created_at: string;
  readonly updated_at: string;
  readonly revision_created_at: string;
}

interface ProjectListPage {
  readonly items: readonly ProjectListItem[];
  readonly next_cursor: string | null;
  readonly has_more: boolean;
}

interface CreatedProject extends ProjectListItem {
  readonly description: string;
}

const bodyCanary = "E2E-PROJECT-LIST-BODY-CANARY-007";
const cursorCanary = "E2E_PROJECT_LIST_CURSOR_CANARY_007";

function sortKey(project: ProjectListItem): string {
  return `${project.created_at}\u0000${project.project_id}`;
}

async function issueWriteHeaders(
  request: APIRequestContext,
  origin: string,
): Promise<Record<string, string>> {
  const session = await request.get("/api/v1/security/session", {
    headers: { Origin: origin },
  });
  expect(session.status()).toBe(200);
  const body = (await session.json()) as { readonly csrf_token: string };
  return { Origin: origin, "X-CSRF-Token": body.csrf_token };
}

test("E2E-INT-007 keeps Project keyset pagination stable", async ({
  baseURL,
  browserAudit,
  context,
  page,
}) => {
  expect(baseURL).toBeDefined();
  const origin = new URL(baseURL ?? "http://invalid").origin;
  const writeHeaders = await issueWriteHeaders(context.request, origin);
  const created: CreatedProject[] = [];

  for (let value = 1; value <= 5; value += 1) {
    const response = await context.request.post("/api/v1/projects", {
      data: {
        title: `List Project ${value}`,
        description: `${bodyCanary}-${value}`,
      },
      headers: writeHeaders,
    });
    expect(response.status()).toBe(201);
    created.push((await response.json()) as CreatedProject);
  }
  const expected = [...created].sort((left, right) =>
    sortKey(left) < sortKey(right) ? 1 : -1,
  );

  await context.clearCookies();
  const firstResponse = await context.request.get("/api/v1/projects?limit=2");
  expect(firstResponse.status()).toBe(200);
  expectSecurityHeaders(firstResponse.headers(), "api");
  expect(firstResponse.headers().etag).toBeUndefined();
  expect(firstResponse.headers().location).toBeUndefined();
  const first = (await firstResponse.json()) as ProjectListPage;
  expect(first.items).toHaveLength(2);
  expect(first.has_more).toBe(true);
  expect(first.next_cursor).toBeTruthy();
  expect(JSON.stringify(first)).not.toContain("description");
  expect(JSON.stringify(first)).not.toContain(bodyCanary);

  const secondWriteHeaders = await issueWriteHeaders(context.request, origin);
  const unread = expected[2];
  if (unread === undefined) {
    throw new Error("five seeded Projects must have a third item");
  }
  const revised = await context.request.put(
    `/api/v1/projects/${unread.project_id}`,
    {
      data: {
        title: "Revised during E2E pagination",
        description: `${bodyCanary}-revised`,
      },
      headers: { ...secondWriteHeaders, "If-Match": '"1"' },
    },
  );
  expect(revised.status()).toBe(200);

  const inserted = await context.request.post("/api/v1/projects", {
    data: { title: "Newest E2E Project", description: `${bodyCanary}-new` },
    headers: secondWriteHeaders,
  });
  expect(inserted.status()).toBe(201);
  const insertedBody = (await inserted.json()) as CreatedProject;
  await context.clearCookies();

  const observed: ProjectListItem[] = [...first.items];
  let cursor = first.next_cursor;
  while (cursor !== null) {
    const response = await context.request.get("/api/v1/projects", {
      params: { limit: 2, cursor },
    });
    expect(response.status()).toBe(200);
    const body = (await response.json()) as ProjectListPage;
    observed.push(...body.items);
    cursor = body.next_cursor;
  }

  const observedIds = observed.map((item) => item.project_id);
  expect(observedIds).toEqual(expected.map((item) => item.project_id));
  expect(new Set(observedIds).size).toBe(5);
  expect(observedIds).not.toContain(insertedBody.project_id);
  const revisedItem = observed.find(
    (item) => item.project_id === unread.project_id,
  );
  expect(revisedItem?.title).toBe("Revised during E2E pagination");
  expect(revisedItem?.concurrency_version).toBe(2);
  expect(revisedItem?.created_at).toBe(unread.created_at);
  expect(JSON.stringify(observed)).not.toContain("description");
  expect(JSON.stringify(observed)).not.toContain(bodyCanary);

  const newFirstResponse = await context.request.get(
    "/api/v1/projects?limit=2",
  );
  expect(newFirstResponse.status()).toBe(200);
  const newFirst = (await newFirstResponse.json()) as ProjectListPage;
  expect(newFirst.items[0]?.project_id).toBe(insertedBody.project_id);

  const invalid = await context.request.get("/api/v1/projects", {
    params: { cursor: cursorCanary },
  });
  expect(invalid.status()).toBe(400);
  const invalidBody = (await invalid.json()) as {
    readonly error: { readonly code: string };
  };
  expect(invalidBody.error.code).toBe("INVALID_CURSOR");
  expect(JSON.stringify(invalidBody)).not.toContain(cursorCanary);

  const routeResponse = await page.goto("/not-a-real-route");
  expect(routeResponse?.status()).toBe(200);
  await expect(page.getByRole("heading", { name: "页面不存在" })).toBeVisible();
  expectCleanBrowserAudit(browserAudit);
});
import type { APIRequestContext } from "@playwright/test";
