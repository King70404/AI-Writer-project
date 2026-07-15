import type { Page, Route } from "@playwright/test";

export interface RequestGate {
  readonly reached: Promise<void>;
  readonly release: () => void;
}

export async function gateFirstRequest(
  page: Page,
  path: string,
): Promise<RequestGate> {
  let signalReached: () => void = () => undefined;
  let signalRelease: () => void = () => undefined;
  let used = false;
  const reached = new Promise<void>((resolve) => {
    signalReached = resolve;
  });
  const released = new Promise<void>((resolve) => {
    signalRelease = resolve;
  });

  const handler = async (route: Route): Promise<void> => {
    if (used || route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    used = true;
    signalReached();
    await released;
    await route.fallback();
  };

  await page.route((url) => url.pathname === path, handler);
  return { reached, release: signalRelease };
}
