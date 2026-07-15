import { expect, test as base } from "@playwright/test";

import { installBrowserAudit, type BrowserAudit } from "./network-guard";

interface E2EFixtures {
  readonly browserAudit: BrowserAudit;
}

export const test = base.extend<E2EFixtures>({
  browserAudit: [
    async ({ baseURL, context }, use, testInfo) => {
      if (baseURL === undefined) {
        throw new Error("The E2E Playwright config must define baseURL.");
      }

      const { audit, finalize } = await installBrowserAudit(
        context,
        baseURL,
        testInfo,
      );
      await use(audit);
      await finalize();
    },
    { auto: true },
  ],
});

export { expect };
