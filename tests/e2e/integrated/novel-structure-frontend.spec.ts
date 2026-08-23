import { expectCleanBrowserAudit } from "../support/assertions";
import { expect, test } from "../support/fixture";

const projectTitle = "E2E Novel Structure Frontend 017";
const projectDescription = "E2E-NOVEL-STRUCTURE-PROJECT-CANARY-017";

test("E2E-INT-017 exercises the unified Novel Structure frontend flow", async ({
  baseURL,
  browserAudit,
  page,
}) => {
  expect(baseURL).toBeDefined();
  browserAudit.allowOneExpectedSessionCookie();
  const requests: Array<{
    readonly method: string;
    readonly path: string;
    readonly ifMatch: string | undefined;
  }> = [];
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (
      path.includes("/outline") ||
      path.includes("/volumes") ||
      path.includes("/chapters")
    ) {
      requests.push({
        method: request.method(),
        path,
        ifMatch: request.headers()["if-match"],
      });
    }
  });

  await page.goto("/projects");
  await page.getByRole("textbox", { name: "项目标题" }).fill(projectTitle);
  await page
    .getByRole("textbox", { name: "项目简介" })
    .fill(projectDescription);
  await page.getByRole("button", { name: "创建项目" }).click();
  const projectLink = page.getByRole("link", { name: "查看新项目" });
  const projectPath = await projectLink.getAttribute("href");
  expect(projectPath).toMatch(/^\/projects\/prj_[0-9A-HJKMNP-TV-Z]{26}$/u);
  await projectLink.click();
  const structureLink = page.getByRole("link", { name: "小说结构" });
  const structurePath = `${projectPath}/structure`;
  expect(await structureLink.getAttribute("href")).toBe(structurePath);
  const projectId = projectPath?.split("/")[2] ?? "invalid-project";
  const outlineApi = `/api/v1/projects/${projectId}/outline`;
  browserAudit.allowExpectedConsoleHttpFailure(outlineApi, 404);
  await structureLink.click();
  await expect(page).toHaveURL(`${browserAudit.allowedOrigin}${structurePath}`);
  await expect(
    page.getByRole("heading", { level: 2, name: "小说结构" }),
  ).toBeVisible();
  await expect(page.getByText("当前尚未创建大纲。")).toBeVisible();
  await expect(page.getByText("请先创建卷")).toBeVisible();

  const outline = page
    .getByRole("heading", { name: "大纲" })
    .locator("xpath=ancestor::section[1]");
  await outline.getByLabel("标题").fill("远征总纲");
  await outline
    .getByLabel("梗概")
    .fill("E2E-NOVEL-STRUCTURE-OUTLINE-CANARY-017-V1");
  const outlineCreate = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === outlineApi,
  );
  await outline.getByRole("button", { name: "创建大纲" }).click();
  expect((await outlineCreate).headers().etag).toBe('"1"');
  await expect(page.getByText("大纲已创建。")).toBeVisible();

  const createVolume = page
    .getByRole("heading", { name: "创建卷" })
    .locator("xpath=ancestor::form[1]");
  const volumesApi = `/api/v1/projects/${projectId}/volumes`;
  const addVolume = async (
    title: string,
    summary: string,
    position: number,
  ) => {
    await createVolume.getByLabel("标题").fill(title);
    await createVolume.getByLabel("梗概").fill(summary);
    await createVolume.getByLabel("顺序").fill(String(position));
    const responsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === volumesApi,
    );
    await createVolume.getByRole("button", { name: "创建卷" }).click();
    const response = await responsePromise;
    expect(response.status()).toBe(201);
    expect(response.headers().etag).toBe('"1"');
  };
  await addVolume("第一卷·启程", "E2E-NOVEL-STRUCTURE-VOLUME-CANARY-017-A", 1);
  await addVolume("第二卷·风暴", "E2E-NOVEL-STRUCTURE-VOLUME-CANARY-017-B", 2);
  const volumeButtons = page
    .getByRole("heading", { name: "卷" })
    .locator("xpath=ancestor::section[1]")
    .locator("ol")
    .getByRole("button");
  await expect(volumeButtons).toHaveText(["1. 第一卷·启程", "2. 第二卷·风暴"]);
  await page.getByRole("button", { name: "1. 第一卷·启程" }).click();
  await expect(page.getByText("当前卷：第一卷·启程")).toBeVisible();

  const firstVolumeGet = requests.find(
    (request) =>
      request.method === "GET" &&
      /^\/api\/v1\/volumes\/vol_/u.test(request.path),
  );
  expect(firstVolumeGet).toBeDefined();
  const selectedVolumeId =
    firstVolumeGet?.path.split("/").at(-1) ?? "invalid-volume";
  const chaptersApi = `/api/v1/projects/${projectId}/volumes/${selectedVolumeId}/chapters`;
  const createChapter = page
    .getByRole("heading", { name: "创建章" })
    .locator("xpath=ancestor::form[1]");
  const addChapter = async (
    title: string,
    summary: string,
    position: number,
  ) => {
    await createChapter.getByLabel("标题").fill(title);
    await createChapter.getByLabel("梗概").fill(summary);
    await createChapter.getByLabel("顺序").fill(String(position));
    const responsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === chaptersApi,
    );
    await createChapter.getByRole("button", { name: "创建章" }).click();
    const response = await responsePromise;
    expect(response.status()).toBe(201);
    expect(response.headers().etag).toBe('"1"');
  };
  await addChapter(
    "第一章·入城",
    "E2E-NOVEL-STRUCTURE-CHAPTER-CANARY-017-A",
    1,
  );
  await addChapter(
    "第二章·夜雨",
    "E2E-NOVEL-STRUCTURE-CHAPTER-CANARY-017-B",
    2,
  );
  const chapterButtons = page
    .getByRole("heading", { name: "章" })
    .locator("xpath=ancestor::section[1]")
    .locator("ol")
    .getByRole("button");
  await expect(chapterButtons).toHaveText(["1. 第一章·入城", "2. 第二章·夜雨"]);

  await outline.getByLabel("标题").fill("远征总纲·终版");
  await outline.getByLabel("梗概").fill("总纲已完整替换");
  await outline.getByRole("button", { name: "保存大纲" }).click();
  await expect(page.getByText("大纲已更新。")).toBeVisible();

  const editVolume = page
    .getByRole("heading", { name: "编辑所选卷" })
    .locator("xpath=ancestor::form[1]");
  await editVolume.getByLabel("标题").fill("第一卷·启程终版");
  await editVolume.getByLabel("梗概").fill("第一卷已完整替换");
  await editVolume.getByRole("button", { name: "保存卷" }).click();
  await expect(page.getByText("卷已更新。")).toBeVisible();

  const firstChapterButton = page.getByRole("button", {
    name: "1. 第一章·入城",
  });
  await firstChapterButton.click();
  await expect(firstChapterButton).toHaveAttribute("aria-pressed", "true");
  const editChapter = page
    .getByRole("heading", { name: "编辑所选章" })
    .locator("xpath=ancestor::form[1]");
  await expect(editChapter.getByLabel("标题")).toHaveValue("第一章·入城");
  await editChapter.getByLabel("标题").fill("第一章·入城终版");
  await editChapter.getByLabel("梗概").fill("第一章已完整替换");
  await editChapter.getByRole("button", { name: "保存章" }).click();
  await expect(page.getByText("章已更新。")).toBeVisible();

  await expect(outline.getByLabel("标题")).toHaveValue("远征总纲·终版");
  await expect(
    page.getByRole("button", { name: "1. 第一卷·启程终版" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "1. 第一章·入城终版" }),
  ).toBeVisible();
  expect(
    requests
      .filter((request) => request.method === "PUT")
      .map((request) => request.ifMatch),
  ).toEqual(['"1"', '"1"', '"1"']);
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
  expect(await page.evaluate(() => sessionStorage.length)).toBe(0);
  expect(page.url()).not.toMatch(/etag|csrf|summary|draft/iu);
  expectCleanBrowserAudit(browserAudit);
});
