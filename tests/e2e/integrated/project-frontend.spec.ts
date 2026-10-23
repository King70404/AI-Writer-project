import {
  expectCleanBrowserAudit,
  expectSecurityHeaders,
} from "../support/assertions";
import { expect, test } from "../support/fixture";

const titleCanary = "E2E Project Frontend 008";
const descriptionCanary = "E2E-PROJECT-FRONTEND-DESCRIPTION-CANARY-008";

test("E2E-INT-008 exercises the Project list and creation UI", async ({
  baseURL,
  browserAudit,
  context,
  page,
}) => {
  expect(baseURL).toBeDefined();
  const origin = new URL(baseURL ?? "http://invalid").origin;
  expect(origin).toBe(browserAudit.allowedOrigin);
  browserAudit.allowOneExpectedSessionCookie();

  const projectListUrls: string[] = [];
  const healthRequestFailures: Array<{
    readonly error: string;
    readonly method: string;
    readonly path: string;
  }> = [];
  page.on("request", (request) => {
    const target = new URL(request.url());
    if (request.method() === "GET" && target.pathname === "/api/v1/projects") {
      projectListUrls.push(target.toString());
    }
  });
  page.on("requestfailed", (request) => {
    const target = new URL(request.url());
    if (target.pathname.startsWith("/api/v1/health/")) {
      healthRequestFailures.push({
        error: request.failure()?.errorText ?? "",
        method: request.method(),
        path: target.pathname,
      });
    }
  });

  const direct = await page.goto("/projects");
  expect(direct?.status()).toBe(200);
  if (direct === null) {
    throw new Error(
      "direct Project navigation must return a document response",
    );
  }
  expectSecurityHeaders(direct.headers(), "html");
  await expect(
    page.getByRole("heading", { level: 2, name: "书架" }),
  ).toBeVisible();
  await expect(page.getByText("还没有项目")).toBeVisible();
  expect(
    browserAudit.events.filter(
      (event) =>
        event.type === "request" &&
        event.method === "GET" &&
        event.path === "/api/v1/security/session",
    ),
  ).toHaveLength(0);

  browserAudit.allowOneExpectedHealthCancellation();
  await page.getByRole("link", { name: "首页" }).click();
  await expect(
    page.getByRole("heading", { name: "写作首页" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "书架", exact: true }).click();
  await expect(page.getByText("还没有项目")).toBeVisible();
  expect(healthRequestFailures.length).toBeLessThanOrEqual(1);
  if (healthRequestFailures.length === 1) {
    expect(healthRequestFailures).toEqual([
      {
        error: "net::ERR_ABORTED",
        method: "GET",
        path: "/api/v1/health/ready",
      },
    ]);
  }

  await page.getByRole("textbox", { name: "书名" }).fill(titleCanary);
  await page
    .getByRole("textbox", { name: "一句话简介（可选）" })
    .fill(descriptionCanary);
  await page.getByRole("button", { name: "创建小说" }).click();

  const firstCard = page.getByRole("listitem").filter({ hasText: titleCanary });
  await expect(firstCard).toBeVisible();
  await expect(firstCard).toHaveAttribute(
    "data-project-id",
    /^prj_[0-9A-HJKMNP-TV-Z]{26}$/u,
  );
  await expect(firstCard.locator(".project-card__id")).toHaveCount(0);
  await expect(firstCard.getByText(/当前修订|并发版本/u)).toHaveCount(0);
  const projectId = await firstCard.getAttribute("data-project-id");
  await expect(
    firstCard.getByRole("link", { name: "打开小说" }),
  ).toHaveAttribute("href", `/projects/${projectId}`);
  expect(
    (await (
      await context.request.get(`/api/v1/projects/${projectId}`)
    ).json()) as unknown,
  ).toMatchObject({ revision_number: 1, concurrency_version: 1 });
  await expect(page.getByRole("textbox", { name: "书名" })).toHaveValue("");
  await expect(
    page.getByRole("textbox", { name: "一句话简介（可选）" }),
  ).toHaveValue("");
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toMatch(
    /csrf|token/iu,
  );
  expect(await page.evaluate(() => JSON.stringify(sessionStorage))).not.toMatch(
    /csrf|token/iu,
  );
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
  expect(await page.evaluate(() => sessionStorage.length)).toBe(0);

  await page.reload();
  await expect(firstCard).toBeVisible();
  await expect(page.getByText(descriptionCanary)).toHaveCount(0);

  const session = await context.request.get("/api/v1/security/session", {
    headers: { Origin: origin },
  });
  expect(session.status()).toBe(200);
  const sessionBody = (await session.json()) as { readonly csrf_token: string };
  for (let index = 1; index <= 20; index += 1) {
    const response = await context.request.post("/api/v1/projects", {
      data: {
        title: `Seeded Project ${String(index).padStart(2, "0")}`,
        description: `${descriptionCanary}-${index}`,
      },
      headers: { Origin: origin, "X-CSRF-Token": sessionBody.csrf_token },
    });
    expect(response.status()).toBe(201);
  }

  await page.reload();
  await expect(page.getByRole("listitem")).toHaveCount(20);
  await expect(page.getByRole("button", { name: "加载更多" })).toBeVisible();
  await expect(page.getByText(titleCanary)).toHaveCount(0);
  const sessionsBeforeLoadMore = browserAudit.events.filter(
    (event) =>
      event.type === "request" &&
      event.method === "GET" &&
      event.path === "/api/v1/security/session",
  ).length;
  const locationBeforeLoadMore = page.url();

  await page.getByRole("button", { name: "加载更多" }).click();

  await expect(page.getByRole("listitem")).toHaveCount(21);
  await expect(page.getByText(titleCanary)).toBeVisible();
  await expect(page.getByRole("button", { name: "加载更多" })).toHaveCount(0);
  expect(
    new Set(
      await page
        .locator("[data-project-id]")
        .evaluateAll((nodes) =>
          nodes.map((node) => node.getAttribute("data-project-id")),
        ),
    ).size,
  ).toBe(21);
  expect(page.url()).toBe(locationBeforeLoadMore);
  expect(
    browserAudit.events.filter(
      (event) =>
        event.type === "request" &&
        event.method === "GET" &&
        event.path === "/api/v1/security/session",
    ).length,
  ).toBe(sessionsBeforeLoadMore);
  expect(projectListUrls.length).toBeGreaterThanOrEqual(4);
  for (const rawUrl of projectListUrls) {
    const target = new URL(rawUrl);
    expect(target.searchParams.has("total")).toBe(false);
    expect(target.searchParams.has("offset")).toBe(false);
  }
  await expect(page.getByText(descriptionCanary, { exact: false })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("button", { name: /详情|编辑|删除|历史|搜索|筛选|排序/ }),
  ).toHaveCount(0);

  const notFound = await page.goto("/not-a-real-route");
  expect(notFound?.status()).toBe(200);
  await expect(page.getByRole("heading", { name: "页面不存在" })).toBeVisible();
  expectCleanBrowserAudit(browserAudit);
});
