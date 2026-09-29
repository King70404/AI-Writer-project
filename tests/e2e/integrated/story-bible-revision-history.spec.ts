import { request as playwrightRequest } from "@playwright/test";

import {
  expectCleanBrowserAudit,
  expectNoEngineeringMetadata,
} from "../support/assertions";
import { expect, test } from "../support/fixture";

test("E2E-INT-013 browses immutable Story Bible history with keyset paging", async ({
  baseURL,
  browserAudit,
  page,
}) => {
  expect(baseURL).toBeDefined();
  const origin = new URL(baseURL ?? "http://invalid").origin;
  const external = await playwrightRequest.newContext({ baseURL: origin });
  let projectId = "";
  let storyBibleId = "";
  try {
    const session = await external.get("/api/v1/security/session", {
      headers: { Origin: origin },
    });
    expect(session.status()).toBe(200);
    const csrf = ((await session.json()) as { readonly csrf_token: string })
      .csrf_token;
    const writeHeaders = {
      Origin: origin,
      "X-CSRF-Token": csrf,
    };
    const project = await external.post("/api/v1/projects", {
      data: {
        title: "E2E Story Bible History Owner 013",
        description: "E2E-STORY-BIBLE-HISTORY-PROJECT-CANARY-013",
      },
      headers: writeHeaders,
    });
    expect(project.status()).toBe(201);
    projectId = ((await project.json()) as { readonly project_id: string })
      .project_id;
    const created = await external.post(
      `/api/v1/projects/${projectId}/story-bible`,
      {
        data: {
          title: "E2E Story Bible History Revision 01 013",
          content: "E2E-STORY-BIBLE-HISTORY-CONTENT-CANARY-013-01",
        },
        headers: writeHeaders,
      },
    );
    expect(created.status()).toBe(201);
    storyBibleId = (
      (await created.json()) as { readonly story_bible_id: string }
    ).story_bible_id;
    let etag = created.headers().etag ?? "missing-etag";
    for (let number = 2; number <= 21; number += 1) {
      const revised = await external.put(
        `/api/v1/story-bibles/${storyBibleId}`,
        {
          data: {
            title: `E2E Story Bible History Revision ${String(number).padStart(2, "0")} 013`,
            content: `E2E-STORY-BIBLE-HISTORY-CONTENT-CANARY-013-${String(number).padStart(2, "0")}`,
          },
          headers: { ...writeHeaders, "If-Match": etag },
        },
      );
      expect(revised.status()).toBe(200);
      etag = revised.headers().etag ?? "missing-etag";
      expect(etag).toBe(`"${number}"`);
    }
  } finally {
    await external.dispose();
  }

  const securityRequests: string[] = [];
  const historyRequests: string[] = [];
  page.on("request", (request) => {
    const target = new URL(request.url());
    if (target.pathname === "/api/v1/security/session") {
      securityRequests.push(target.pathname);
    }
    if (target.pathname.includes("/revisions")) {
      historyRequests.push(target.toString());
    }
  });
  await page.goto(`/projects/${projectId}/story-bible/history`);
  await expect(
    page.getByRole("heading", { name: "小说设定修订历史", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".project-revision-card")).toHaveCount(20);
  await expectNoEngineeringMetadata(page);
  await expect(page.locator(".project-revision-card time")).toHaveCount(20);
  await expect(page.locator(".project-revision-card h3")).toHaveText(
    Array.from({ length: 20 }, (_, index) => `修订 ${21 - index}`),
  );
  await expect(
    page.getByText("E2E-STORY-BIBLE-HISTORY-CONTENT-CANARY-013-01"),
  ).toHaveCount(0);
  expect(securityRequests).toHaveLength(0);

  const urlBeforeLoadMore = page.url();
  await page.getByRole("button", { name: "加载更多" }).click();
  await expect(page.locator(".project-revision-card")).toHaveCount(21);
  expect(page.url()).toBe(urlBeforeLoadMore);
  const revisionOne = page.locator(".project-revision-card").filter({
    has: page.getByRole("heading", { name: "修订 1", exact: true }),
  });
  await revisionOne.getByRole("button", { name: "查看正文" }).click();
  await expect(
    page.getByText("E2E-STORY-BIBLE-HISTORY-CONTENT-CANARY-013-01"),
  ).toBeVisible();
  await expectNoEngineeringMetadata(page);
  await expect(
    page.getByRole("button", {
      name: /回滚|恢复|采用|删除|Diff|编辑历史/u,
    }),
  ).toHaveCount(0);
  expect(
    historyRequests.some((value) => new URL(value).searchParams.has("total")),
  ).toBe(false);
  expect(securityRequests).toHaveLength(0);
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
  expect(await page.evaluate(() => sessionStorage.length)).toBe(0);
  expect(page.url()).not.toMatch(/cursor|content|revision_id/iu);
  expectCleanBrowserAudit(browserAudit);
});
