import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { NovelStructurePage } from "../../frontend/src/features/novel-structure/pages/NovelStructurePage";
import { NovelStructureApiError } from "../../frontend/src/features/novel-structure/api/client";
import {
  chapterResponse,
  secondChapterId,
  secondVolumeId,
  structureClient,
  structureError,
  structureProjectId,
  versionedChapter,
  versionedOutline,
  versionedVolume,
  volumeResponse,
} from "./novel-structure-support";

function renderWorkspace(
  client = structureClient(),
  path = `/projects/${structureProjectId}/structure`,
) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="projects/:projectId/structure"
          element={<NovelStructurePage client={client} />}
        />
        <Route path="projects" element={<h1>项目列表</h1>} />
        <Route path="projects/:projectId" element={<h1>项目详情</h1>} />
      </Routes>
    </MemoryRouter>,
  );
}

function form(name: string): HTMLElement {
  return screen.getByRole("heading", { name }).closest("form")!;
}

describe("Novel Structure workspace", () => {
  it("renders a safe invalid route without making API requests", () => {
    const client = structureClient();
    renderWorkspace(client, "/projects/bad/structure");
    expect(
      screen.getByRole("heading", { name: "Project编号无效" }),
    ).toBeVisible();
    expect(client.getOutline).not.toHaveBeenCalled();
    expect(client.listVolumes).not.toHaveBeenCalled();
  });

  describe("creation behaviors", () => {
    function emptyClient() {
      return structureClient({
        getOutline: vi
          .fn()
          .mockRejectedValue(
            structureError("outline_not_found", "该项目尚未创建大纲。"),
          ),
        listVolumes: vi.fn().mockResolvedValue([]),
      });
    }

    it("loads an empty workspace without invalid Chapter reads", async () => {
      const client = emptyClient();
      renderWorkspace(client);
      expect(await screen.findByText("当前尚未创建大纲。")).toBeVisible();
      expect(screen.getByText("请先创建卷")).toBeVisible();
      expect(client.listChapters).not.toHaveBeenCalled();
      expect(client.getChapter).not.toHaveBeenCalled();
    });

    it("creates an outline while preserving title spacing and summary newlines", async () => {
      const user = userEvent.setup();
      const client = emptyClient();
      renderWorkspace(client);
      await screen.findByText("当前尚未创建大纲。");
      const outline = screen
        .getByRole("heading", { name: "大纲" })
        .closest("section")!;
      await user.type(within(outline).getByLabelText("标题"), " 新总纲 ");
      await user.type(
        within(outline).getByLabelText("梗概"),
        "第一行{enter}第二行",
      );
      await user.click(
        within(outline).getByRole("button", { name: "创建大纲" }),
      );
      expect(await screen.findByText("大纲已创建。")).toBeVisible();
      expect(client.createOutline).toHaveBeenCalledExactlyOnceWith(
        structureProjectId,
        {
          title: " 新总纲 ",
          summary: "第一行\n第二行",
        },
      );
    });

    it("creates volumes with initial and edited order, selecting each new volume", async () => {
      const user = userEvent.setup();
      const client = emptyClient();
      vi.mocked(client.createVolume)
        .mockResolvedValueOnce(versionedVolume())
        .mockResolvedValueOnce(
          versionedVolume(1, {
            volume_id: secondVolumeId,
            title: "第二卷",
            position: 2,
          }),
        );
      renderWorkspace(client);
      await screen.findByText("请先创建卷");
      const volumeForm = form("创建卷");
      const fields = within(volumeForm);
      await user.type(fields.getByLabelText("标题"), "第一卷");
      await user.type(fields.getByLabelText("梗概"), "卷梗概");
      expect(fields.getByLabelText("顺序")).toHaveValue(1);
      await user.click(fields.getByRole("button", { name: "创建卷" }));
      expect(await screen.findByText("卷已创建。已选中新卷。")).toBeVisible();
      expect(client.createVolume).toHaveBeenCalledExactlyOnceWith(
        structureProjectId,
        {
          title: "第一卷",
          summary: "卷梗概",
          position: 1,
        },
      );
      expect(screen.queryByText("请先创建卷")).not.toBeInTheDocument();
      expect(fields.getByLabelText("标题")).toHaveValue("");
      expect(fields.getByLabelText("顺序")).toHaveValue(2);
      await user.type(fields.getByLabelText("标题"), "第二卷");
      await user.type(fields.getByLabelText("梗概"), "第二卷梗概");
      await user.clear(fields.getByLabelText("顺序"));
      expect(fields.getByLabelText("顺序")).toHaveValue(null);
      await user.type(fields.getByLabelText("顺序"), "2");
      await user.click(fields.getByRole("button", { name: "创建卷" }));
      expect(await screen.findByText("当前卷：第二卷")).toBeVisible();
      expect(client.createVolume).toHaveBeenCalledTimes(2);
      expect(client.createVolume).toHaveBeenLastCalledWith(structureProjectId, {
        title: "第二卷",
        summary: "第二卷梗概",
        position: 2,
      });
      expect(screen.getByRole("button", { name: "2. 第二卷" })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
      expect(fields.getByLabelText("顺序")).toHaveValue(3);
    });

    it("creates chapters in the selected volume with initial and edited order", async () => {
      const user = userEvent.setup();
      const client = structureClient({
        listVolumes: vi.fn().mockResolvedValue([
          volumeResponse(1, {
            volume_id: secondVolumeId,
            title: "第二卷",
            position: 2,
          }),
        ]),
        getVolume: vi.fn().mockResolvedValue(
          versionedVolume(1, {
            volume_id: secondVolumeId,
            title: "第二卷",
            position: 2,
          }),
        ),
        listChapters: vi.fn().mockResolvedValue([]),
        createChapter: vi
          .fn()
          .mockResolvedValueOnce(
            versionedChapter(1, { volume_id: secondVolumeId }),
          )
          .mockResolvedValueOnce(
            versionedChapter(1, {
              chapter_id: secondChapterId,
              volume_id: secondVolumeId,
              title: "第二章",
              position: 2,
            }),
          ),
      });
      renderWorkspace(client);
      await screen.findByText("当前卷：第二卷");
      const fields = within(form("创建章"));
      expect(client.getChapter).not.toHaveBeenCalled();
      await user.type(fields.getByLabelText("标题"), "第一章");
      await user.type(fields.getByLabelText("梗概"), "章梗概");
      expect(fields.getByLabelText("顺序")).toHaveValue(1);
      await user.click(fields.getByRole("button", { name: "创建章" }));
      expect(await screen.findByText("章已创建。已选中新章。")).toBeVisible();
      expect(client.createChapter).toHaveBeenCalledExactlyOnceWith(
        structureProjectId,
        secondVolumeId,
        {
          title: "第一章",
          summary: "章梗概",
          position: 1,
        },
      );
      expect(fields.getByLabelText("标题")).toHaveValue("");
      expect(fields.getByLabelText("顺序")).toHaveValue(2);
      await user.type(fields.getByLabelText("标题"), "第二章");
      await user.type(fields.getByLabelText("梗概"), "第二章梗概");
      await user.clear(fields.getByLabelText("顺序"));
      expect(fields.getByLabelText("顺序")).toHaveValue(null);
      await user.type(fields.getByLabelText("顺序"), "2");
      await user.click(fields.getByRole("button", { name: "创建章" }));
      expect(
        await screen.findByRole("button", { name: "2. 第二章" }),
      ).toHaveAttribute("aria-pressed", "true");
      expect(client.createChapter).toHaveBeenCalledTimes(2);
      expect(client.createChapter).toHaveBeenLastCalledWith(
        structureProjectId,
        secondVolumeId,
        {
          title: "第二章",
          summary: "第二章梗概",
          position: 2,
        },
      );
      expect(fields.getByLabelText("顺序")).toHaveValue(3);
    });
  });

  it.each([
    ["创建卷", "createVolume"],
    ["编辑所选卷", "updateVolume"],
    ["创建章", "createChapter"],
    ["编辑所选章", "updateChapter"],
  ] as const)(
    "keeps a cleared position empty and rejects submission in %s",
    async (heading, operation) => {
      const user = userEvent.setup();
      const client = structureClient({
        createVolume: vi.fn().mockResolvedValue(
          versionedVolume(1, {
            volume_id: secondVolumeId,
            position: 3,
          }),
        ),
        createChapter: vi.fn().mockResolvedValue(
          versionedChapter(1, {
            chapter_id: secondChapterId,
            position: 3,
          }),
        ),
      });
      renderWorkspace(client);
      await screen.findByRole("heading", { name: "编辑所选章" });
      const target = form(heading);
      const fields = within(target);
      const title = fields.getByLabelText("标题");
      if ((title as HTMLInputElement).value === "")
        await user.type(title, "测试");
      const position = fields.getByLabelText("顺序");
      await user.clear(position);
      expect(position).toHaveValue(null);
      expect(position).not.toHaveAttribute("value", "NaN");
      // Exercise application validation independently of native number constraints.
      fireEvent.submit(target);
      expect(fields.getByText("顺序必须是正整数。")).toBeVisible();
      expect(client[operation]).not.toHaveBeenCalled();
      await user.type(position, "3");
      expect(position).toHaveValue(3);
      await user.click(fields.getByRole("button"));
      await waitFor(() => expect(client[operation]).toHaveBeenCalledOnce());
      expect(vi.mocked(client[operation]).mock.calls[0]).toContainEqual(
        expect.objectContaining({ position: 3 }),
      );
    },
  );

  it("loads sorted resources and selects chapters and volumes", async () => {
    const user = userEvent.setup();
    const secondVolume = volumeResponse(1, {
      volume_id: secondVolumeId,
      title: "第二卷",
      position: 2,
    });
    const secondChapter = chapterResponse(1, {
      chapter_id: secondChapterId,
      title: "第二章",
      position: 2,
    });
    const getVolume = vi
      .fn()
      .mockResolvedValueOnce(versionedVolume())
      .mockResolvedValueOnce(
        versionedVolume(1, {
          volume_id: secondVolumeId,
          title: "第二卷",
          position: 2,
        }),
      );
    const listChapters = vi
      .fn()
      .mockResolvedValueOnce([chapterResponse(), secondChapter])
      .mockResolvedValueOnce([]);
    const getChapter = vi.fn().mockResolvedValue(versionedChapter());
    const client = structureClient({
      listVolumes: vi.fn().mockResolvedValue([volumeResponse(), secondVolume]),
      getVolume,
      listChapters,
      getChapter,
    });
    renderWorkspace(client);
    expect(
      await screen.findByRole("button", { name: "1. 第一卷" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "2. 第二卷" })).toBeVisible();
    expect(screen.getByRole("button", { name: "1. 第一章" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await user.click(screen.getByRole("button", { name: "2. 第二章" }));
    await waitFor(() => expect(getChapter).toHaveBeenCalledTimes(2));
    await user.click(screen.getByRole("button", { name: "2. 第二卷" }));
    await waitFor(() => expect(getVolume).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("当前卷：第二卷")).toBeVisible();
    expect(screen.getByText("当前卷尚未创建章。")).toBeVisible();
  });

  it("updates the outline with its exact ETag", async () => {
    const user = userEvent.setup();
    const client = structureClient({
      updateOutline: vi
        .fn()
        .mockResolvedValue(versionedOutline(2, { title: "更新总纲" })),
    });
    renderWorkspace(client);
    await screen.findByRole("heading", { name: "编辑所选章" });
    const outline = screen
      .getByRole("heading", { name: "大纲" })
      .closest("section")!;
    await user.clear(within(outline).getByLabelText("标题"));
    await user.type(within(outline).getByLabelText("标题"), "更新总纲");
    await user.click(within(outline).getByRole("button", { name: "保存大纲" }));
    expect(await screen.findByText("大纲已更新。")).toBeVisible();
    expect(client.updateOutline).toHaveBeenCalledExactlyOnceWith(
      outlineIdMatcher(),
      structureProjectId,
      expect.objectContaining({ title: "更新总纲" }),
      '"1"',
    );
  });

  it("updates the selected volume with its exact ETag", async () => {
    const user = userEvent.setup();
    const client = structureClient({
      updateVolume: vi
        .fn()
        .mockResolvedValue(versionedVolume(2, { title: "更新第一卷" })),
    });
    renderWorkspace(client);
    await screen.findByRole("heading", { name: "编辑所选章" });
    const fields = within(form("编辑所选卷"));
    await user.clear(fields.getByLabelText("标题"));
    await user.type(fields.getByLabelText("标题"), "更新第一卷");
    await user.click(fields.getByRole("button", { name: "保存卷" }));
    expect(await screen.findByText("卷已更新。")).toBeVisible();
    expect(client.updateVolume).toHaveBeenCalledExactlyOnceWith(
      versionedVolume().resource.volume_id,
      structureProjectId,
      expect.objectContaining({ title: "更新第一卷" }),
      '"1"',
    );
  });

  it("updates the selected chapter and edited order with its exact ETag", async () => {
    const user = userEvent.setup();
    const client = structureClient({
      updateChapter: vi
        .fn()
        .mockResolvedValue(versionedChapter(2, { title: "更新第一章" })),
    });
    renderWorkspace(client);
    await screen.findByRole("heading", { name: "编辑所选章" });
    const fields = within(form("编辑所选章"));
    await user.clear(fields.getByLabelText("标题"));
    await user.type(fields.getByLabelText("标题"), "更新第一章");
    await user.clear(fields.getByLabelText("顺序"));
    await user.type(fields.getByLabelText("顺序"), "1");
    await user.click(fields.getByRole("button", { name: "保存章" }));
    expect(await screen.findByText("章已更新。")).toBeVisible();
    expect(client.updateChapter).toHaveBeenCalledExactlyOnceWith(
      versionedChapter().resource.chapter_id,
      structureProjectId,
      versionedChapter().resource.volume_id,
      expect.objectContaining({ title: "更新第一章", position: 1 }),
      '"1"',
    );
  });

  it("keeps drafts and surfaces 409 and 412 errors without automatic retry", async () => {
    const user = userEvent.setup();
    const conflict = structureError(
      "conflict",
      "内容已被其他操作更新。草稿已保留，请重新读取后再处理。",
    );
    const position = structureError(
      "position_conflict",
      "该顺序已被占用，请选择其他正整数。",
    );
    const updateOutline = vi.fn().mockRejectedValue(conflict);
    const updateVolume = vi.fn().mockRejectedValue(position);
    const client = structureClient({ updateOutline, updateVolume });
    renderWorkspace(client);
    await screen.findByRole("button", { name: "1. 第一卷" });
    const outline = screen
      .getByRole("heading", { name: "大纲" })
      .closest("section")!;
    const outlineTitle = within(outline).getByLabelText("标题");
    await user.clear(outlineTitle);
    await user.type(outlineTitle, "本地大纲草稿");
    await user.click(within(outline).getByRole("button", { name: "保存大纲" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("草稿已保留");
    expect(outlineTitle).toHaveValue("本地大纲草稿");
    expect(updateOutline).toHaveBeenCalledOnce();

    const volumeEdit = form("编辑所选卷");
    await user.clear(within(volumeEdit).getByLabelText("顺序"));
    await user.type(within(volumeEdit).getByLabelText("顺序"), "2");
    await user.click(
      within(volumeEdit).getByRole("button", { name: "保存卷" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("顺序已被占用");
    expect(within(volumeEdit).getByLabelText("顺序")).toHaveValue(2);
    expect(updateVolume).toHaveBeenCalledOnce();
  });

  it("shows safe request IDs, local summary/position errors, and selection load failures", async () => {
    const user = userEvent.setup();
    const secondVolume = volumeResponse(1, {
      volume_id: secondVolumeId,
      title: "第二卷",
      position: 2,
    });
    const selectionError = new NovelStructureApiError({
      kind: "unavailable",
      code: "SAFE_SELECTION_ERROR",
      message: "所选卷暂时无法读取。",
      requestId: "req_structure_safe",
    });
    const client = structureClient({
      listVolumes: vi.fn().mockResolvedValue([volumeResponse(), secondVolume]),
      getVolume: vi
        .fn()
        .mockResolvedValueOnce(versionedVolume())
        .mockRejectedValueOnce(selectionError),
    });
    renderWorkspace(client);
    await screen.findByRole("button", { name: "2. 第二卷" });

    const createVolume = form("创建卷");
    await user.type(within(createVolume).getByLabelText("标题"), "无效卷");
    await user.type(within(createVolume).getByLabelText("梗概"), "\u2028");
    await user.clear(within(createVolume).getByLabelText("顺序"));
    await user.type(within(createVolume).getByLabelText("顺序"), "0");
    fireEvent.submit(createVolume);
    expect(within(createVolume).getByText(/梗概最多为2000/u)).toBeVisible();
    expect(within(createVolume).getByText("顺序必须是正整数。")).toBeVisible();
    expect(client.createVolume).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "2. 第二卷" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "所选卷暂时无法读取。",
    );
    expect(screen.getByText("请求编号：req_structure_safe")).toBeVisible();
  });

  it("fails safely when a hostile non-Error load rejection is received", async () => {
    renderWorkspace(
      structureClient({
        getOutline: vi.fn().mockRejectedValue({ private: "canary" }),
        listVolumes: vi.fn().mockResolvedValue([]),
      }),
    );
    expect(
      await screen.findByRole("heading", { name: "小说结构加载失败" }),
    ).toBeVisible();
    expect(screen.getByRole("alert")).not.toHaveTextContent("canary");
  });

  it("validates locally, disables while submitting, and handles not-found and retryable load errors", async () => {
    const user = userEvent.setup();
    let resolveCreate:
      ((value: ReturnType<typeof versionedOutline>) => void) | undefined;
    const createOutline = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCreate = resolve;
        }),
    );
    const client = structureClient({
      getOutline: vi
        .fn()
        .mockRejectedValue(structureError("outline_not_found", "missing")),
      listVolumes: vi.fn().mockResolvedValue([]),
      createOutline,
    });
    renderWorkspace(client);
    await screen.findByText("当前尚未创建大纲。");
    const outline = screen
      .getByRole("heading", { name: "大纲" })
      .closest("section")!;
    await user.click(within(outline).getByRole("button", { name: "创建大纲" }));
    expect(within(outline).getByText(/标题必填/u)).toBeVisible();
    expect(createOutline).not.toHaveBeenCalled();
    await user.type(within(outline).getByLabelText("标题"), "延迟创建");
    await user.click(within(outline).getByRole("button", { name: "创建大纲" }));
    expect(
      within(outline).getByRole("button", { name: "正在提交…" }),
    ).toBeDisabled();
    resolveCreate?.(versionedOutline());
    expect(await screen.findByText("大纲已创建。")).toBeVisible();

    const notFound = structureClient({
      getOutline: vi
        .fn()
        .mockRejectedValue(
          structureError("project_not_found", "指定项目不存在。"),
        ),
      listVolumes: vi.fn().mockResolvedValue([]),
    });
    const view = renderWorkspace(notFound);
    expect(
      await screen.findByRole("heading", { name: "项目不存在" }),
    ).toBeVisible();
    view.unmount();

    const listVolumes = vi
      .fn()
      .mockRejectedValueOnce(structureError("unavailable", "服务暂时不可用。"))
      .mockResolvedValueOnce([]);
    renderWorkspace(
      structureClient({
        getOutline: vi
          .fn()
          .mockRejectedValue(structureError("outline_not_found", "missing")),
        listVolumes,
      }),
    );
    expect(
      await screen.findByRole("heading", { name: "小说结构加载失败" }),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "重新加载" }));
    expect(await screen.findByText("当前尚未创建大纲。")).toBeVisible();
    expect(listVolumes).toHaveBeenCalledTimes(2);
  });
});

function outlineIdMatcher(): string {
  return "out_01ARZ3NDEKTSV4RRFFQ69G5FAV";
}
