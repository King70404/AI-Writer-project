import { request as playwrightRequest } from "@playwright/test";

import { expectCleanBrowserAudit } from "../support/assertions";
import { expect, test } from "../support/fixture";

const projectTitle = "E2E Character Frontend Owner 015";
const sharedName = "E2E Character Shared Name 015";
const profileA = "E2E-CHARACTER-PROFILE-CANARY-015-A\nprivate line";
const profileB = "E2E-CHARACTER-PROFILE-CANARY-015-B";
const revisedProfile = "E2E-CHARACTER-PROFILE-CANARY-015-A-V2";
const externalProfile = "E2E-CHARACTER-PROFILE-CANARY-015-A-V3";
const localProfile = "E2E-CHARACTER-PROFILE-CANARY-015-A-V4-LOCAL";

test("E2E-INT-015 exercises Character frontend creation, stable listing, and ETag conflict recovery", async ({
  baseURL,
  browserAudit,
  page,
}) => {
  expect(baseURL).toBeDefined();
  const origin = new URL(baseURL ?? "http://invalid").origin;
  browserAudit.allowOneExpectedSessionCookie();
  const requests: Array<{
    readonly method: string;
    readonly path: string;
    readonly ifMatch: string | undefined;
  }> = [];
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (path.includes("/characters")) {
      requests.push({
        method: request.method(),
        path,
        ifMatch: request.headers()["if-match"],
      });
    }
  });

  await page.goto("/projects");
  await page.getByRole("textbox", { name: "项目标题" }).fill(projectTitle);
  await page.getByRole("button", { name: "创建项目" }).click();
  await page.getByRole("link", { name: "查看新项目" }).click();
  const characterLink = page.getByRole("link", { name: "查看角色" });
  await expect(characterLink).toBeVisible();
  const listPath = await characterLink.getAttribute("href");
  expect(listPath).toMatch(
    /^\/projects\/prj_[0-9A-HJKMNP-TV-Z]{26}\/characters$/u,
  );
  const projectId = listPath?.split("/")[2] ?? "invalid-project";
  const listApiPath = `/api/v1/projects/${projectId}/characters`;
  await characterLink.click();
  await expect(page.getByText("该Project尚未创建角色。")).toBeVisible();
  expect(
    requests.filter(
      (request) => request.method === "GET" && request.path === listApiPath,
    ),
  ).toHaveLength(1);

  const createCharacter = async (role: string, profile: string) => {
    await page.getByRole("textbox", { name: "角色名称" }).fill(sharedName);
    await page.getByRole("textbox", { name: "角色定位" }).fill(role);
    await page
      .getByRole("textbox", { name: "角色档案（纯文本）" })
      .fill(profile);
    const responsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === listApiPath,
    );
    await page.getByRole("button", { name: "创建角色" }).click();
    const response = await responsePromise;
    expect(response.status()).toBe(201);
    expect(response.headers().etag).toBe('"1"');
    return (await response.json()) as {
      readonly character_id: string;
    };
  };

  const first = await createCharacter("Lead", profileA);
  await expect(page.getByText("角色创建成功。")).toBeVisible();
  await expect(page.getByText(profileA)).toHaveCount(0);
  expect(
    requests.filter(
      (request) => request.method === "GET" && request.path === listApiPath,
    ),
  ).toHaveLength(1);
  const second = await createCharacter("Rival", profileB);
  expect(second.character_id).not.toBe(first.character_id);
  await expect(
    page.getByRole("link", { name: new RegExp(first.character_id, "u") }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: new RegExp(second.character_id, "u") }),
  ).toBeVisible();
  await expect(page.getByText(profileB)).toHaveCount(0);

  const editorPath = `${listPath}/${first.character_id}`;
  await page
    .getByRole("link", { name: new RegExp(first.character_id, "u") })
    .click();
  await expect(
    page.getByRole("textbox", { name: "角色档案（纯文本）" }),
  ).toHaveValue(profileA);
  const directApiPath = `/api/v1/characters/${first.character_id}`;
  await page
    .getByRole("textbox", { name: "角色档案（纯文本）" })
    .fill(revisedProfile);
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByText("角色修订已保存。")).toBeVisible();
  await expect(
    page.getByText("ConcurrencyVersion").locator("xpath=following-sibling::dd"),
  ).toHaveText("2");
  await page.reload();
  await expect(
    page.getByRole("textbox", { name: "角色档案（纯文本）" }),
  ).toHaveValue(revisedProfile);

  const external = await playwrightRequest.newContext({ baseURL: origin });
  try {
    const security = await external.get("/api/v1/security/session", {
      headers: { Origin: origin },
    });
    const token = ((await security.json()) as { readonly csrf_token: string })
      .csrf_token;
    const response = await external.put(directApiPath, {
      data: { name: sharedName, role: "External", profile: externalProfile },
      headers: {
        Origin: origin,
        "X-CSRF-Token": token,
        "If-Match": '"2"',
      },
    });
    expect(response.status()).toBe(200);
    expect(response.headers().etag).toBe('"3"');
  } finally {
    await external.dispose();
  }

  await page
    .getByRole("textbox", { name: "角色档案（纯文本）" })
    .fill(localProfile);
  const getsBeforeConflict = requests.filter(
    (request) => request.method === "GET" && request.path === directApiPath,
  ).length;
  browserAudit.allowExpectedConsoleHttpFailure(directApiPath, 412);
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "检测到版本冲突" }),
  ).toBeFocused();
  await expect(
    page.getByRole("textbox", { name: "角色档案（纯文本）" }),
  ).toHaveValue(localProfile);
  expect(
    requests.filter(
      (request) => request.method === "GET" && request.path === directApiPath,
    ),
  ).toHaveLength(getsBeforeConflict);
  await page.getByRole("button", { name: "读取服务器最新版本" }).click();
  await expect(page.getByText(/已读取服务器版本 3/u)).toBeVisible();
  await page.getByRole("button", { name: "保留草稿并重建基线" }).click();
  const putsBeforeFinal = requests.filter(
    (request) => request.method === "PUT" && request.path === directApiPath,
  ).length;
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByText("角色修订已保存。")).toBeVisible();
  const characterPuts = requests.filter(
    (request) => request.method === "PUT" && request.path === directApiPath,
  );
  expect(characterPuts).toHaveLength(putsBeforeFinal + 1);
  expect(characterPuts.map((request) => request.ifMatch)).toEqual([
    '"1"',
    '"2"',
    '"3"',
  ]);
  await expect(
    page.getByText("ConcurrencyVersion").locator("xpath=following-sibling::dd"),
  ).toHaveText("4");
  await page.reload();
  await expect(
    page.getByRole("textbox", { name: "角色档案（纯文本）" }),
  ).toHaveValue(localProfile);
  expect(page.url()).toContain(editorPath ?? "/invalid");
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
  expect(await page.evaluate(() => sessionStorage.length)).toBe(0);
  expect(page.url()).not.toMatch(/etag|csrf|cursor|profile|draft/iu);
  await page.goto(listPath ?? "/invalid-list");
  await expect(page.getByRole("heading", { name: "角色管理" })).toBeVisible();
  await page.goto("/characters/not-supported");
  await expect(page.getByRole("heading", { name: "页面不存在" })).toBeVisible();
  expectCleanBrowserAudit(browserAudit);
});
