import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppRouter } from "../../frontend/src/app/AppRouter";
import {
  BackupError,
  type BackupItem,
  type BackupVerification,
} from "../../frontend/src/features/author-backup/api/backups";
import {
  BackupManager,
  type BackupClient,
} from "../../frontend/src/features/author-backup/components/BackupManager";

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
const item: BackupItem = {
  backup_id: backupId,
  file_bytes: 2048,
  readable: true,
  created_at: "2026-10-20T08:30:00Z",
  summary,
};

function fakeClient(overrides: Partial<BackupClient> = {}): BackupClient {
  return {
    list: vi.fn<BackupClient["list"]>().mockResolvedValue([item]),
    create: vi.fn<BackupClient["create"]>().mockResolvedValue(item),
    verify: vi.fn<BackupClient["verify"]>().mockResolvedValue({
      backup_id: backupId,
      status: "valid",
      problem: null,
      summary,
    }),
    restore: vi.fn<BackupClient["restore"]>().mockResolvedValue({
      backup_id: backupId,
      target_name: "恢复副本",
      summary,
    }),
    downloadUrl: (id: string) => `/api/v1/backups/${id}/download`,
    ...overrides,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("author backup page", () => {
  it("is reachable from the main navigation", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockImplementation(() =>
          Promise.resolve(Response.json({ items: [] })),
        ),
    );
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppRouter />
      </MemoryRouter>,
    );
    const navigation = screen.getByRole("navigation", { name: "主要导航" });
    await userEvent.click(
      within(navigation).getByRole("link", { name: "数据备份" }),
    );
    expect(
      await screen.findByRole("heading", { name: "备份与恢复" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("还没有备份。建议在大量修改前先备份一次。"),
    ).toBeInTheDocument();
  });

  it("creates a verified backup, then lists counts and a download link", async () => {
    const list = vi
      .fn<BackupClient["list"]>()
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([item]);
    const client = fakeClient({ list });
    render(<BackupManager client={client} />);
    expect(await screen.findByText(/还没有备份/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "立即备份" }));
    expect(await screen.findByText(/已创建并校验备份/)).toBeInTheDocument();
    expect(client.create).toHaveBeenCalledOnce();
    const card = await screen.findByRole("listitem");
    expect(within(card).getByText(/1 部小说 · 2 章/)).toBeInTheDocument();
    expect(within(card).getByText(/4\s*条已确认事实/)).toBeInTheDocument();
    expect(within(card).getByText("文件大小：2.0 KB")).toBeInTheDocument();
    expect(
      within(card).getByRole("link", { name: "下载备份" }),
    ).toHaveAttribute("href", `/api/v1/backups/${backupId}/download`);
  });

  it.each<[BackupVerification["status"], RegExp]>([
    ["valid", /校验通过/],
    ["corrupt", /校验失败/],
    ["incompatible", /不兼容的版本/],
  ])("shows %s verification results", async (status, text) => {
    const client = fakeClient({
      verify: vi.fn<BackupClient["verify"]>().mockResolvedValue({
        backup_id: backupId,
        status,
        problem: status === "valid" ? null : "BACKUP_CORRUPT",
        summary: null,
      }),
    });
    render(<BackupManager client={client} />);
    await userEvent.click(
      await screen.findByRole("button", { name: "校验完整性" }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(text);
    expect(client.verify).toHaveBeenCalledWith(backupId);
  });

  it("requires a plain folder name and explicit confirmation before restoring", async () => {
    const client = fakeClient();
    render(<BackupManager client={client} />);
    await userEvent.click(
      await screen.findByRole("button", { name: "恢复到新文件夹" }),
    );
    const restore = screen.getByRole("button", { name: "恢复为新副本" });
    const name = screen.getByLabelText("新副本文件夹名称");
    expect(restore).toBeDisabled();
    await userEvent.type(name, "../escape");
    expect(name).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText(/不能以点或短横线开头/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox"));
    expect(restore).toBeDisabled();
    await userEvent.clear(name);
    await userEvent.type(name, "恢复副本");
    expect(restore).toBeEnabled();
    await userEvent.click(restore);
    expect(client.restore).toHaveBeenCalledExactlyOnceWith(
      backupId,
      "恢复副本",
    );
    const result = await screen.findByRole("heading", {
      name: "已恢复为独立副本",
    });
    expect(result.parentElement).toHaveTextContent("“恢复副本”文件夹");
    expect(result.parentElement).toHaveTextContent("-DataRoot");
    await userEvent.click(screen.getByRole("button", { name: "取消恢复" }));
    expect(screen.queryByLabelText("新副本文件夹名称")).not.toBeInTheDocument();
  });

  it("keeps the form and shows the server reason when restore is refused", async () => {
    const client = fakeClient({
      restore: vi
        .fn<BackupClient["restore"]>()
        .mockRejectedValue(
          new BackupError("该文件夹已存在且不是空文件夹。", "X"),
        ),
    });
    render(<BackupManager client={client} />);
    await userEvent.click(
      await screen.findByRole("button", { name: "恢复到新文件夹" }),
    );
    await userEvent.type(screen.getByLabelText("新副本文件夹名称"), "occupied");
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "恢复为新副本" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("不是空文件夹");
    expect(screen.getByLabelText("新副本文件夹名称")).toHaveValue("occupied");
  });

  it("reports load, create and verify failures and can reload", async () => {
    const list = vi
      .fn<BackupClient["list"]>()
      .mockRejectedValueOnce(new BackupError("无法连接本地服务。", "N"))
      .mockResolvedValueOnce([
        {
          ...item,
          readable: false,
          created_at: null,
          summary: null,
        },
      ]);
    const client = fakeClient({
      list,
      create: vi
        .fn<BackupClient["create"]>()
        .mockRejectedValue(new BackupError("另一个备份任务正在进行。", "B")),
      verify: vi.fn<BackupClient["verify"]>().mockRejectedValue(new Error("x")),
    });
    render(<BackupManager client={client} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("无法连接");
    await userEvent.click(screen.getByRole("button", { name: "重新加载" }));
    const card = await screen.findByRole("listitem");
    expect(within(card).getByText(/无法读取备份清单/)).toBeInTheDocument();
    expect(within(card).getByText("时间未知")).toBeInTheDocument();
    expect(within(card).queryByRole("link")).not.toBeInTheDocument();
    expect(
      within(card).queryByRole("button", { name: "恢复到新文件夹" }),
    ).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "立即备份" }));
    await waitFor(() =>
      expect(screen.getAllByRole("alert")[0]).toHaveTextContent(
        "另一个备份任务",
      ),
    );
    await userEvent.click(
      within(card).getByRole("button", { name: "校验完整性" }),
    );
    expect(await within(card).findByRole("alert")).toHaveTextContent(
      "没有改变",
    );
  });

  it("marks legacy backups that need an explicit upgrade in the copy", async () => {
    const client = fakeClient({
      list: vi.fn<BackupClient["list"]>().mockResolvedValue([
        {
          ...item,
          summary: { ...summary, requires_upgrade: true },
        },
      ]),
    });
    render(<BackupManager client={client} />);
    expect(
      await screen.findByText(/旧版数据，恢复后需在副本中显式升级/),
    ).toBeInTheDocument();
  });
});
