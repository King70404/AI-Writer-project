import type {
  BrowserContext,
  Download,
  Page,
  TestInfo,
} from "@playwright/test";
import { describe, expect, it, vi } from "vitest";

import { installBrowserAudit } from "../e2e/support/network-guard";

async function fixture(title = "E2E-INT-020 Novel text export flow") {
  const on = vi.fn<(event: string, callback: unknown) => void>();
  const page = { on } as unknown as Page;
  const context = {
    clearPermissions: vi.fn().mockResolvedValue(undefined),
    route: vi.fn().mockResolvedValue(undefined),
    routeWebSocket: vi.fn().mockResolvedValue(undefined),
    on: vi.fn(),
    pages: () => [page],
    cookies: vi.fn().mockResolvedValue([]),
  } as unknown as BrowserContext;
  const testInfo = {
    title,
    status: "passed",
    expectedStatus: "passed",
    attach: vi.fn().mockResolvedValue(undefined),
  } as unknown as TestInfo;
  const installed = await installBrowserAudit(
    context,
    "http://127.0.0.1:18120",
    testInfo,
  );
  const handler = on.mock.calls.find(
    ([event]) => event === "download",
  )?.[1] as (download: Download) => void;
  return { ...installed, handler };
}

function download(
  filename = "归途.txt",
  url = "blob:http://127.0.0.1:18120/example",
) {
  const cancel = vi.fn().mockResolvedValue(undefined);
  return {
    value: {
      suggestedFilename: () => filename,
      url: () => url,
      cancel,
    } as unknown as Download,
    cancel,
  };
}

describe("export-specific browser download audit", () => {
  it("permits exactly one explicitly expected same-origin TXT download", async () => {
    const { audit, handler, finalize } = await fixture();
    audit.allowOneExpectedManuscriptDownload("归途.txt");
    const event = download();
    handler(event.value);
    expect(event.cancel).not.toHaveBeenCalled();
    expect(audit.unexpectedDownloads).toEqual([]);
    await expect(finalize()).resolves.toBeUndefined();
  });

  it("keeps downloads forbidden by default", async () => {
    const { audit, handler, finalize } = await fixture(
      "E2E-INT-019 AI writing assistance flow",
    );
    expect(() =>
      audit.allowOneExpectedManuscriptDownload("归途.txt"),
    ).toThrow();
    const event = download();
    handler(event.value);
    expect(event.cancel).toHaveBeenCalledOnce();
    await expect(finalize()).rejects.toThrow("Unexpected download");
  });

  it.each(["../novel.txt", "bad\u0001.txt", "book.pdf", ".txt"])(
    "rejects unsafe filename %j",
    async (filename) => {
      const { audit } = await fixture();
      expect(() =>
        audit.allowOneExpectedManuscriptDownload(filename),
      ).toThrow();
    },
  );

  it.each([
    ["wrong.txt", "blob:http://127.0.0.1:18120/example"],
    ["归途.txt", "blob:https://example.invalid/example"],
    ["归途.txt", "http://127.0.0.1:18120/export.txt"],
  ])("rejects a mismatched download %s %s", async (filename, url) => {
    const { audit, handler, finalize } = await fixture();
    audit.allowOneExpectedManuscriptDownload("归途.txt");
    const event = download(filename, url);
    handler(event.value);
    expect(event.cancel).toHaveBeenCalledOnce();
    await expect(finalize()).rejects.toThrow("Unexpected download");
  });

  it("rejects duplicate allowances and duplicate downloads", async () => {
    const { audit, handler, finalize } = await fixture();
    audit.allowOneExpectedManuscriptDownload("归途.txt");
    expect(() =>
      audit.allowOneExpectedManuscriptDownload("归途.txt"),
    ).toThrow();
    const first = download();
    const second = download();
    handler(first.value);
    handler(second.value);
    expect(first.cancel).not.toHaveBeenCalled();
    expect(second.cancel).toHaveBeenCalledOnce();
    await expect(finalize()).rejects.toThrow("Unexpected download");
  });

  it("fails when the required download never occurs", async () => {
    const { audit, finalize } = await fixture();
    audit.allowOneExpectedManuscriptDownload("归途.txt");
    await expect(finalize()).rejects.toThrow(
      "Expected manuscript download was not observed",
    );
  });
});

describe("backup-specific browser download audit", () => {
  const backupId = "20261020T083000Z-0123456789ab";
  const filename = `aiwebnovel-backup-${backupId}.zip`;
  const url = `http://127.0.0.1:18120/api/v1/backups/${backupId}/download`;
  const title = "E2E-INT-022 Author backup flow";

  it("permits exactly one same-origin backup archive download", async () => {
    const { audit, handler, finalize } = await fixture(title);
    audit.allowOneExpectedBackupDownload();
    const event = download(filename, url);
    handler(event.value);
    expect(event.cancel).not.toHaveBeenCalled();
    await expect(finalize()).resolves.toBeUndefined();
  });

  it("is limited to the backup scenario and a single allowance", async () => {
    const other = await fixture();
    expect(() => other.audit.allowOneExpectedBackupDownload()).toThrow();
    const { audit } = await fixture(title);
    audit.allowOneExpectedBackupDownload();
    expect(() => audit.allowOneExpectedBackupDownload()).toThrow();
    expect(() =>
      audit.allowOneExpectedManuscriptDownload("归途.txt"),
    ).toThrow();
  });

  it.each([
    ["aiwebnovel-backup-x.zip", url],
    [filename, "http://127.0.0.1:18120/api/v1/backups/other/download"],
    [filename, `blob:http://127.0.0.1:18120/${backupId}`],
    [filename, `https://example.invalid/api/v1/backups/${backupId}/download`],
  ])("rejects a mismatched backup download %s %s", async (name, target) => {
    const { audit, handler, finalize } = await fixture(title);
    audit.allowOneExpectedBackupDownload();
    const event = download(name, target);
    handler(event.value);
    expect(event.cancel).toHaveBeenCalledOnce();
    await expect(finalize()).rejects.toThrow("Unexpected download");
  });

  it("fails when the expected backup download never occurs", async () => {
    const { audit, finalize } = await fixture(title);
    audit.allowOneExpectedBackupDownload();
    await expect(finalize()).rejects.toThrow(
      "Expected backup download was not observed",
    );
  });
});
