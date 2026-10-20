import { afterEach, describe, expect, it, vi } from "vitest";

import { securitySession } from "../../frontend/src/api/security-session";
import {
  BackupError,
  backupClient,
  backupErrorMessage,
  isPlainFolderName,
  parseBackupItem,
} from "../../frontend/src/features/author-backup/api/backups";
import {
  formatBytes,
  formatCreatedAt,
} from "../../frontend/src/features/author-backup/formatting";

const backupId = "20261020T083000Z-0123456789ab";
const summary = {
  schema_revision: "0009_add_story_memory",
  requires_upgrade: false,
  counts: {
    projects: 1,
    chapters: 2,
    chapter_revisions: 3,
    confirmed_facts: 4,
    workflow_runs: 5,
  },
};
const item = {
  backup_id: backupId,
  file_bytes: 2048,
  readable: true,
  created_at: "2026-10-20T08:30:00Z",
  summary,
};

function errorResponse(status: number, code: string) {
  return Response.json(
    {
      error: {
        code,
        message: "server text",
        details: {},
        retryable: false,
        suggested_action: null,
      },
      request_id: "req_backup",
    },
    { status },
  );
}

function stubSession() {
  return vi.spyOn(securitySession, "getValidSession").mockResolvedValue({
    csrfToken: "backup-proof",
    expiresAtMilliseconds: Date.now() + 60_000,
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  securitySession.clear();
});

describe("backup API client", () => {
  it("lists with a plain GET and no session or CSRF", async () => {
    const session = stubSession();
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json({ items: [item] }));
    vi.stubGlobal("fetch", fetcher);
    await expect(backupClient.list()).resolves.toEqual([item]);
    const [url, options] = fetcher.mock.calls[0];
    expect(url).toBe("/api/v1/backups");
    expect(options?.method).toBe("GET");
    expect(new Headers(options?.headers).has("X-CSRF-Token")).toBe(false);
    expect(session).not.toHaveBeenCalled();
  });

  it("sends CSRF-guarded create, verify and confirmed restore exactly once", async () => {
    stubSession();
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json(item, { status: 201 }))
      .mockResolvedValueOnce(
        Response.json({
          backup_id: backupId,
          status: "valid",
          problem: null,
          summary,
        }),
      )
      .mockResolvedValueOnce(
        Response.json({ backup_id: backupId, target_name: "副本", summary }),
      );
    vi.stubGlobal("fetch", fetcher);
    await expect(backupClient.create()).resolves.toEqual(item);
    await expect(backupClient.verify(backupId)).resolves.toMatchObject({
      status: "valid",
    });
    await expect(backupClient.restore(backupId, "副本")).resolves.toEqual({
      backup_id: backupId,
      target_name: "副本",
      summary,
    });
    expect(fetcher).toHaveBeenCalledTimes(3);
    const calls = fetcher.mock.calls.map(([url, options]) => ({
      url,
      method: options?.method,
      csrf: new Headers(options?.headers).get("X-CSRF-Token"),
      body: options?.body,
    }));
    expect(calls).toEqual([
      {
        url: "/api/v1/backups",
        method: "POST",
        csrf: "backup-proof",
        body: "{}",
      },
      {
        url: `/api/v1/backups/${backupId}/verify`,
        method: "POST",
        csrf: "backup-proof",
        body: "{}",
      },
      {
        url: `/api/v1/backups/${backupId}/restore`,
        method: "POST",
        csrf: "backup-proof",
        body: JSON.stringify({ target_name: "副本", confirm_new_copy: true }),
      },
    ]);
  });

  it("rejects malformed identifiers before any request", async () => {
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    await expect(backupClient.verify("../escape")).rejects.toThrow(
      "备份编号无效",
    );
    await expect(backupClient.restore("x", "copy")).rejects.toBeInstanceOf(
      BackupError,
    );
    expect(() => backupClient.downloadUrl("../../etc")).toThrow();
    expect(backupClient.downloadUrl(backupId)).toBe(
      `/api/v1/backups/${backupId}/download`,
    );
    expect(fetcher).not.toHaveBeenCalled();
  });

  it.each([
    [409, "BACKUP_BUSY", "另一个备份任务正在进行"],
    [404, "BACKUP_NOT_FOUND", "找不到这个备份"],
    [422, "BACKUP_CORRUPT", "未通过完整性校验"],
    [409, "BACKUP_INCOMPATIBLE", "不兼容的版本"],
    [422, "RESTORE_TARGET_INVALID", "新的文件夹名称"],
    [409, "RESTORE_TARGET_NOT_EMPTY", "不是空文件夹"],
    [503, "BACKUP_UNAVAILABLE", "暂时无法备份"],
    [503, "SOMETHING_NEW", "当前创作数据没有改变"],
  ])("maps %i %s to author text", async (status, code, text) => {
    stubSession();
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(errorResponse(status, code)),
    );
    const error = await backupClient
      .restore(backupId, "copy")
      .catch((reason: unknown) => reason);
    expect(error).toBeInstanceOf(BackupError);
    expect((error as BackupError).code).toBe(code);
    expect(backupErrorMessage(error)).toContain(text);
  });

  it("clears the local session on 403 and reports network failures", async () => {
    stubSession();
    const clear = vi.spyOn(securitySession, "clear");
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValueOnce(errorResponse(403, "CSRF_INVALID"))
        .mockRejectedValueOnce(new TypeError("offline")),
    );
    await expect(backupClient.create()).rejects.toThrow("安全会话已失效");
    expect(clear).toHaveBeenCalled();
    await expect(backupClient.list()).rejects.toThrow("无法连接本地服务");
    expect(backupErrorMessage(new Error("other"))).toContain("没有改变");
  });

  it.each([
    { items: null },
    { items: [{ ...item, backup_id: "../x" }] },
    { items: [{ ...item, file_bytes: -1 }] },
    { items: [{ ...item, readable: "yes" }] },
    { items: [{ ...item, created_at: 5 }] },
    { items: [{ ...item, summary: { ...summary, counts: null } }] },
    {
      items: [
        {
          ...item,
          summary: { ...summary, counts: { ...summary.counts, chapters: 1.5 } },
        },
      ],
    },
    { items: [{ ...item, summary: { ...summary, requires_upgrade: 1 } }] },
  ])("rejects malformed list payloads: %j", async (payload) => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(Response.json(payload)),
    );
    await expect(backupClient.list()).rejects.toThrow("无法读取的备份数据");
  });

  it("rejects malformed verify and restore payloads", async () => {
    stubSession();
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValueOnce(
          Response.json({
            backup_id: backupId,
            status: "maybe",
            problem: null,
            summary: null,
          }),
        )
        .mockResolvedValueOnce(
          Response.json({
            backup_id: backupId,
            status: "valid",
            problem: 1,
            summary: null,
          }),
        )
        .mockResolvedValueOnce(
          Response.json({ backup_id: backupId, target_name: 3, summary }),
        )
        .mockResolvedValueOnce(new Response("not json", { status: 200 })),
    );
    await expect(backupClient.verify(backupId)).rejects.toThrow("无法读取");
    await expect(backupClient.verify(backupId)).rejects.toThrow("无法读取");
    await expect(backupClient.restore(backupId, "c")).rejects.toThrow(
      "无法读取",
    );
    await expect(backupClient.create()).rejects.toThrow("无法读取");
  });

  it("accepts unreadable items without summary", () => {
    expect(
      parseBackupItem({
        ...item,
        readable: false,
        created_at: null,
        summary: null,
      }),
    ).toMatchObject({ readable: false, summary: null });
  });
});

describe("backup folder names and formatting", () => {
  it.each(["副本", "copy_2", "a", "v1.2-final"])("accepts %s", (name) => {
    expect(isPlainFolderName(name)).toBe(true);
  });

  it.each([
    "",
    ".hidden",
    "-a",
    "a-",
    "a b",
    "a/b",
    "a\\b",
    "..",
    "CON",
    "lpt1.txt",
    "e\u0301",
    "x".repeat(65),
  ])("rejects %j", (name) => {
    expect(isPlainFolderName(name)).toBe(false);
  });

  it("formats sizes and timestamps for authors", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(3 * 1024 * 1024)).toBe("3.0 MB");
    expect(formatCreatedAt(null)).toBe("时间未知");
    expect(formatCreatedAt("not a date")).toBe("时间未知");
    expect(formatCreatedAt("2026-10-20T08:30:00Z")).toMatch(/2026/);
  });
});
