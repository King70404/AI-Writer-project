import { expectCleanBrowserAudit } from "../support/assertions";
import { expect, test } from "../support/fixture";

const MODEL_CALL_PATH =
  /\/(?:generate|analyze|analysis|review|reviews|chat\/completions)(?:\/|$)/u;

test("E2E-INT-023 Author workbench: home, chapter navigation, focus mode, in-place model and rule shortcut", async ({
  page,
  browserAudit,
}) => {
  browserAudit.allowOneExpectedSessionCookie();

  // 首页：没有本机记录时不编造继续写作或统计数字。
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "写作首页" })).toBeVisible();
  await expect(page.getByText(/本机还没有最近写作的章节/u)).toBeVisible();
  await expect(page.getByRole("link", { name: "继续写作" })).toHaveCount(0);
  await expect(
    page.getByText(/项目总数|章节总数|今日字数|总字数|待办/u),
  ).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.length)).toBe(0);

  await expect(
    page.getByText("本地后端已连接，数据库基础检查通过。"),
  ).toBeVisible();

  // 书架 → 新建小说 → 卷章结构。
  const navigation = page.getByRole("navigation", { name: "主要导航" });
  await navigation.getByRole("link", { name: "书架" }).click();
  await expect(
    page.getByRole("heading", { level: 2, name: "书架" }),
  ).toBeVisible();
  const title = "灯下长篇";
  await page.getByRole("textbox", { name: "书名" }).fill(title);
  await page.getByRole("button", { name: "创建小说" }).click();
  const projectLink = page.getByRole("link", { name: "打开这本小说" });
  const projectPath = await projectLink.getAttribute("href");
  expect(projectPath).toMatch(/^\/projects\/prj_[0-9A-HJKMNP-TV-Z]{26}$/u);
  const projectId = projectPath!.split("/")[2];
  await projectLink.click();
  browserAudit.allowExpectedConsoleHttpFailure(
    `/api/v1/projects/${projectId}/outline`,
    404,
  );
  await page.getByRole("link", { name: "大纲与章节" }).click();
  await expect(page.getByText("当前尚未创建大纲。")).toBeVisible();
  const outline = page
    .getByRole("heading", { name: "大纲", exact: true })
    .locator("xpath=ancestor::section[1]");
  await outline.getByLabel("标题").fill("灯下总纲");
  await outline.getByRole("button", { name: "创建大纲" }).click();
  await expect(page.getByText("大纲已创建。")).toBeVisible();
  const volumeForm = page
    .getByRole("heading", { name: "创建卷" })
    .locator("xpath=ancestor::form[1]");
  await volumeForm.getByLabel("标题").fill("启程");
  await volumeForm.getByRole("button", { name: "创建卷" }).click();
  await expect(page.getByText("卷已创建。已选中新卷。")).toBeVisible();
  for (const chapterTitle of ["雨夜", "渡口"]) {
    const form = page
      .getByRole("heading", { name: "创建章" })
      .locator("xpath=ancestor::form[1]");
    await form.getByLabel("标题").fill(chapterTitle);
    await form.getByRole("button", { name: "创建章" }).click();
    await expect(
      page.getByRole("button", {
        name: new RegExp(`\\d\\. ${chapterTitle}`, "u"),
      }),
    ).toBeVisible();
  }
  const firstItem = page
    .getByRole("button", { name: "1. 雨夜", exact: true })
    .locator("xpath=ancestor::li[1]");
  const firstPath = await firstItem
    .getByRole("link", { name: "写正文" })
    .getAttribute("href");
  expect(firstPath).toMatch(/\/chapters\/chp_[0-9A-HJKMNP-TV-Z]{26}\/write$/u);
  const firstChapterId = firstPath!.split("/")[4];
  await firstItem.getByRole("link", { name: "写正文" }).click();

  // 三栏写作台与固定状态区。
  const desk = page.getByRole("region", { name: "第1章 / 雨夜" });
  const status = desk.getByRole("region", { name: "写作状态" });
  const editor = desk.getByLabel("章节正文");
  const nav = desk.getByRole("navigation", { name: "卷章导航" });
  const assistant = desk.getByRole("region", { name: "AI写作助手" });
  await expect(editor).toHaveValue("");
  await expect(status.getByRole("status", { name: "保存状态" })).toHaveText(
    "已保存",
  );
  await expect(status.getByLabel("AI 任务状态")).toHaveText(
    "没有进行中的 AI 任务",
  );
  await expect(nav.getByText(title, { exact: true })).toBeVisible();
  await expect(nav.getByRole("link", { name: "第1章 雨夜" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(assistant).toBeVisible();
  const firstBox = await nav.boundingBox();
  const editorBox = await editor.boundingBox();
  const assistantBox = await assistant.boundingBox();
  expect(firstBox!.x + firstBox!.width).toBeLessThanOrEqual(editorBox!.x);
  expect(editorBox!.x + editorBox!.width).toBeLessThanOrEqual(assistantBox!.x);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(await page.evaluate(() => localStorage.length)).toBe(1);
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toMatch(
    /雨夜|灯下|content|etag|csrf/iu,
  );

  // 未保存时切换章节：先保存，再导航；正文保留在服务器。
  const firstText = "雨夜里，旅人推门而入。";
  const contentPath = `/api/v1/chapters/${firstChapterId}/content`;
  const saved = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      new URL(response.url()).pathname === contentPath,
  );
  await editor.fill(firstText);
  await nav.getByRole("link", { name: "第2章 渡口" }).click();
  expect((await saved).status()).toBe(200);
  const secondDesk = page.getByRole("region", { name: "第2章 / 渡口" });
  await expect(secondDesk).toBeVisible();
  await expect(secondDesk.getByLabel("章节正文")).toHaveValue("");
  await secondDesk
    .getByRole("navigation", { name: "卷章导航" })
    .getByRole("link", { name: "第1章 雨夜" })
    .click();
  await expect(editor).toHaveValue(firstText);

  // 专注模式：两侧栏收起，Esc 退出，编辑器内容与焦点按钮保持。
  await status.getByRole("button", { name: "专注写作" }).click();
  await expect(nav).toBeHidden();
  await expect(assistant).toBeHidden();
  await expect(editor).toBeVisible();
  await expect(status.getByRole("status", { name: "保存状态" })).toBeVisible();
  await editor.press("End");
  await page.keyboard.press("Escape");
  await expect(nav).toBeVisible();
  await expect(assistant).toBeVisible();
  await expect(editor).toHaveValue(firstText);
  await expect(status.getByRole("button", { name: "专注写作" })).toBeFocused();

  // 原地添加模型：保存即选中，只保存配置，不发起模型调用。
  const tabs = assistant.getByRole("tablist", { name: "AI 助手分区" });
  await expect(tabs.getByRole("tab", { name: "生成" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  const summary = assistant.getByRole("region", { name: "当前模型" });
  const modelSelect = assistant.getByLabel("使用模型");
  // 模型状态异步读取；先等待读取结束，避免在“添加模型/管理模型”切换期间点击已失效的按钮。
  await expect(summary.getByText("正在读取模型配置…")).toHaveCount(0);
  if ((await summary.getByRole("button", { name: "添加模型" }).count()) > 0) {
    await summary.getByRole("button", { name: "添加模型" }).click();
  } else {
    await summary.getByRole("button", { name: "管理模型" }).click();
    await assistant.getByRole("button", { name: "添加新模型" }).click();
  }
  const nameField = assistant.getByLabel("配置名称", { exact: true });
  await expect(nameField).toBeVisible();
  await nameField.fill("工作台本机模型");
  await assistant.getByLabel("模型名称", { exact: true }).fill("local-writer");
  await assistant
    .getByRole("button", { name: "保存模型配置", exact: true })
    .click();
  await expect(
    assistant.getByText(
      "配置已保存，已选中“工作台本机模型”。密钥不会回显；尚未检查服务连接。",
    ),
  ).toBeVisible();
  await expect(modelSelect.locator("option:checked")).toHaveText(
    "工作台本机模型 · 本地",
  );
  await expect(summary).toContainText("当前模型：工作台本机模型 · 本机模型");

  // 范文捷径：确认规则版本 → 加入本章规划 → 保存 → 回到生成。
  await tabs.getByRole("tab", { name: "准备" }).click();
  const workbench = assistant.getByRole("region", {
    name: "范文分析与章节规划",
    exact: true,
  });
  await workbench
    .getByRole("button", { name: "增加写作规则", exact: true })
    .click();
  await workbench.getByLabel("规则集名称", { exact: true }).fill("雨夜方法");
  await workbench
    .getByRole("textbox", { name: "规则 1 名称", exact: true })
    .fill("动作承接");
  await workbench
    .getByRole("textbox", { name: "规则 1 操作方法", exact: true })
    .fill("先写动作，再给有限回答。");
  await workbench
    .getByRole("textbox", { name: "规则 1 适用范围", exact: true })
    .fill("对峙场景");
  await workbench
    .getByRole("button", { name: "确认保存写作规则", exact: true })
    .click();
  await expect(workbench.getByText(/规则已确认保存为版本 1/u)).toBeVisible();
  const ruleBox = workbench.getByRole("checkbox", {
    name: "雨夜方法 · 版本 1",
    exact: true,
  });
  await expect(ruleBox).not.toBeChecked();
  await workbench
    .getByRole("button", { name: "将此规则加入本章规划", exact: true })
    .click();
  await expect(ruleBox).toBeChecked();
  await expect(ruleBox).toBeFocused();
  await expect(
    assistant.getByText(
      "章节规划有未保存修改；可保存并进入生成准备。此操作不会发送模型请求。",
    ),
  ).toBeVisible();
  await workbench
    .getByLabel("章节重点 1", { exact: true })
    .fill("旅人决定留下");
  await workbench
    .getByRole("button", { name: "保存规划并进入生成准备", exact: true })
    .click();
  await expect(tabs.getByRole("tab", { name: "生成" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(
    assistant.getByRole("button", { name: "准备续写", exact: true }),
  ).toBeFocused();

  // 回到首页：继续写作卡来自本机定位与真实接口标题。
  // 离开写作页会主动取消仍在途的卷章结构请求，这是导航行为而非失败。
  browserAudit.allowOneExpectedLocalCancellation(
    `/api/v1/projects/${projectId}/volumes`,
  );
  await page
    .getByRole("navigation", { name: "主要导航" })
    .getByRole("link", { name: "首页" })
    .click();
  await expect(page).toHaveURL(`${browserAudit.allowedOrigin}/`);
  const continueSection = page.getByRole("region", {
    name: "继续上次创作",
  });
  await expect(continueSection).toBeVisible();
  await expect(continueSection.getByText(title, { exact: true })).toBeVisible();
  await expect(continueSection.getByText("第1章 · 雨夜")).toBeVisible();
  await expect(
    page.getByText("本地后端已连接，数据库基础检查通过。"),
  ).toBeVisible();
  await page.getByRole("link", { name: "继续写作" }).click();
  await expect(page).toHaveURL(
    `${browserAudit.allowedOrigin}/projects/${projectId}/chapters/${firstChapterId}/write`,
  );
  await expect(page.getByLabel("章节正文")).toHaveValue(firstText);

  // 窄屏助手是可关闭的抽屉，调整视口不丢正文与助手输入。
  for (const width of [360, 390, 768, 1024]) {
    await page.setViewportSize({ width, height: 800 });
    const drawer = page.getByRole("dialog", { name: "AI写作助手面板" });
    const open = page.getByRole("button", { name: "显示助手" });
    if (await open.isVisible()) await open.click();
    await expect(drawer).toBeVisible();
    await expect(
      drawer.getByRole("button", { name: "关闭助手" }),
    ).toBeFocused();
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      )
      .toBe(true);
    await drawer.getByRole("tab", { name: "生成" }).click();
    const instruction = drawer.getByLabel("额外要求（可选）");
    if (width === 360) await instruction.fill("保持角色动机");
    await expect(instruction).toHaveValue("保持角色动机");
    await page.keyboard.press("Escape");
    await expect(drawer).not.toBeVisible();
    await expect(open).toBeFocused();
    await expect(page.getByLabel("章节正文")).toHaveValue(firstText);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page
    .getByRole("navigation", { name: "主要导航" })
    .getByRole("link", { name: "书架" })
    .click();
  await expect(
    page.getByRole("link", { name: `继续写作《${title}》` }),
  ).toHaveAttribute(
    "href",
    `/projects/${projectId}/chapters/${firstChapterId}/write`,
  );

  // 零额外模型调用：工作台只读写已有资源。
  expect(
    browserAudit.events.filter(
      (event) => event.type === "request" && MODEL_CALL_PATH.test(event.path),
    ),
  ).toEqual([]);
  expectCleanBrowserAudit(browserAudit);
});
