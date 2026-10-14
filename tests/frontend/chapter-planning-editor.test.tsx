import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";
import { ChapterPlanningEditor } from "../../frontend/src/features/novel-structure/components/ChapterPlanningEditor";
import { AIWritingError } from "../../frontend/src/features/novel-structure/api/ai-writing";
import type {
  ChapterPlan,
  ChapterPlanInput,
  PlanScene,
} from "../../frontend/src/features/novel-structure/api/writing-preparation";
import type { CharacterListPageResponse } from "../../frontend/src/features/character/api/contracts";
import { deferred } from "./chapter-writing-support";
import {
  characterClient,
  characterId,
  characterListItem,
  characterPage,
  secondCharacterId,
} from "./character-support";
import { chapterId, structureProjectId } from "./novel-structure-support";
import {
  chapterPlan,
  preparationClient,
  ruleRevision,
} from "./writing-preparation-support";

function scene(
  id = "courtyard",
  overrides: Partial<PlanScene> = {},
): PlanScene {
  return {
    id,
    title: "庭院试探",
    setting: "雨夜，门前",
    character_ids: [],
    beats: [
      { id: `${id}-listen`, action: "停步听声", change: "察觉来客犹豫" },
      { id: `${id}-ask`, action: "追问旧事", change: "来客改变说辞" },
    ],
    ...overrides,
  };
}

function mount(
  overrides: Partial<ComponentProps<typeof ChapterPlanningEditor>> = {},
) {
  const props: ComponentProps<typeof ChapterPlanningEditor> = {
    projectId: structureProjectId,
    chapterId,
    plan: null,
    rules: [],
    content: "门 开\n😀",
    client: preparationClient(),
    characterClient: characterClient(),
    onSaved: vi.fn(),
    onDirty: vi.fn(),
    onBusy: vi.fn(),
    ...overrides,
  };
  return { ...render(<ChapterPlanningEditor {...props} />), props };
}

function change(name: string, value: string) {
  fireEvent.change(screen.getByRole("textbox", { name }), {
    target: { value },
  });
}

function click(name: string) {
  fireEvent.click(screen.getByRole("button", { name }));
}

describe("chapter planning editor", () => {
  it("creates a first plan with chapter goals, continuity, ordered scenes and beats", async () => {
    const savePlan = vi.fn().mockResolvedValue(chapterPlan());
    const { props } = mount({ client: preparationClient({ savePlan }) });
    expect(screen.getByRole("status")).toHaveTextContent(
      "尚未建立规划。正文 3 / 3000 字",
    );
    expect(
      screen.getByText("先在范文分析下确认写作规则，即可用于本章。"),
    ).toBeVisible();
    change("章节重点 1", "  主人公开始怀疑来客  ");
    click("增加章节重点");
    change("章节重点 2", "  ");
    change("本章要发生的变化", "从信任到试探");
    change("核心冲突", "来客隐藏动机");
    change("承接前文与后续伏笔", "承接上一章来客的承诺");
    fireEvent.change(screen.getByRole("spinbutton", { name: "本章目标字数" }), {
      target: { value: "4000" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: "关联当前小说设定" }));
    click("增加场景");
    change("场景 1 名称", "庭院试探");
    change("场景 1 时间地点与氛围", "雨夜，门前");
    click("为场景 1 增加推进点");
    change("场景 1 推进点 1 行动", "停步听声");
    change("场景 1 推进点 1 变化", "察觉来客犹豫");
    expect(screen.getByRole("status")).toHaveTextContent("规划未保存");
    click("保存章节规划");
    await waitFor(() =>
      expect(props.onSaved).toHaveBeenCalledWith(chapterPlan()),
    );
    expect(savePlan).toHaveBeenCalledExactlyOnceWith(
      structureProjectId,
      chapterId,
      {
        memory_focuses: ["主人公开始怀疑来客"],
        target_characters: 4000,
        chapter_goal: "从信任到试探",
        conflict: "来客隐藏动机",
        continuity_notes: "承接上一章来客的承诺",
        include_story_bible: true,
        writing_rule_revision_ids: [],
        scenes: [
          {
            id: expect.any(String) as unknown,
            title: "庭院试探",
            setting: "雨夜，门前",
            character_ids: [],
            beats: [
              {
                id: expect.any(String) as unknown,
                action: "停步听声",
                change: "察觉来客犹豫",
              },
            ],
          },
        ],
      },
      0,
    );
    expect(props.onDirty).toHaveBeenLastCalledWith(false);
    expect(props.onBusy).toHaveBeenNthCalledWith(1, true);
    expect(props.onBusy).toHaveBeenLastCalledWith(false);
  });

  it("reorders and removes scenes and beats without changing the retained identities", async () => {
    const first = scene();
    const second = scene("bridge", { title: "桥边告别", beats: [] });
    const savePlan = vi.fn().mockResolvedValue(chapterPlan());
    mount({
      plan: chapterPlan({ scenes: [first, second] }),
      client: preparationClient({ savePlan }),
    });
    expect(screen.getByRole("button", { name: "上移场景 1" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "下移场景 2" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "上移推进点 1" })).toBeDisabled();
    click("下移场景 1");
    expect(screen.getByRole("textbox", { name: "场景 1 名称" })).toHaveValue(
      "桥边告别",
    );
    click("上移场景 2");
    click("上移推进点 2");
    expect(
      screen.getByRole("textbox", { name: "场景 1 推进点 1 行动" }),
    ).toHaveValue("追问旧事");
    change("场景 1 推进点 2 行动", "侧身听见门内声音");
    change("场景 1 推进点 2 变化", "发现第三个人");
    click("删除推进点 1");
    click("删除场景 2");
    click("保存章节规划");
    await waitFor(() => expect(savePlan).toHaveBeenCalledOnce());
    expect(savePlan).toHaveBeenCalledWith(
      structureProjectId,
      chapterId,
      expect.objectContaining({
        scenes: [
          {
            ...first,
            beats: [
              {
                id: "courtyard-listen",
                action: "侧身听见门内声音",
                change: "发现第三个人",
              },
            ],
          },
        ],
      }),
      1,
    );
  });

  it("restores persisted values and saves another revision using the latest parent version", async () => {
    const saved = chapterPlan({
      version: 6,
      memory_focuses: ["新重点"],
      scenes: [scene()],
    });
    const savePlan = vi.fn().mockResolvedValue(saved);
    const { props, rerender } = mount({
      plan: chapterPlan({ version: 5 }),
      rules: [ruleRevision()],
      client: preparationClient({ savePlan }),
    });
    expect(
      screen.getByRole("checkbox", { name: "动作方法 · 版本 1" }),
    ).toBeChecked();
    expect(
      screen.getByRole("checkbox", { name: "关联当前小说设定" }),
    ).toBeChecked();
    expect(
      screen.getByRole("textbox", { name: "承接前文与后续伏笔" }),
    ).toHaveValue("承接上一章来客的承诺");
    change("章节重点 1", "新重点");
    click("保存章节规划");
    await waitFor(() => expect(props.onSaved).toHaveBeenCalledWith(saved));
    rerender(<ChapterPlanningEditor {...props} plan={saved} />);
    expect(screen.getByRole("status")).toHaveTextContent("规划已保存 · 版本 6");
    expect(screen.getByRole("textbox", { name: "场景 1 名称" })).toHaveValue(
      "庭院试探",
    );
    change("核心冲突", "修改后的冲突");
    click("保存章节规划");
    await waitFor(() => expect(savePlan).toHaveBeenCalledTimes(2));
    expect(savePlan).toHaveBeenLastCalledWith(
      structureProjectId,
      chapterId,
      expect.objectContaining({ conflict: "修改后的冲突" }),
      6,
    );
    rerender(<ChapterPlanningEditor {...props} key="reopened" plan={saved} />);
    expect(screen.getByRole("textbox", { name: "章节重点 1" })).toHaveValue(
      "新重点",
    );
    expect(
      screen.getByRole("textbox", { name: "场景 1 推进点 2 变化" }),
    ).toHaveValue("来客改变说辞");
  });

  it("retains a conflicting draft and releases the busy state without silently resaving", async () => {
    const savePlan = vi
      .fn()
      .mockRejectedValue(
        new AIWritingError(
          "章节规划已在其他页面更新。当前草稿已保留，请重新加载后再修改。",
          "PLANNING_CONFLICT",
        ),
      );
    const { props } = mount({
      plan: chapterPlan({ version: 4 }),
      client: preparationClient({ savePlan }),
    });
    change("核心冲突", "作者尚未保存的新冲突");
    click("保存章节规划");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "当前草稿已保留",
    );
    expect(screen.getByRole("textbox", { name: "核心冲突" })).toHaveValue(
      "作者尚未保存的新冲突",
    );
    expect(screen.getByRole("status")).toHaveTextContent("规划未保存");
    expect(screen.getByRole("button", { name: "保存章节规划" })).toBeEnabled();
    expect(props.onSaved).not.toHaveBeenCalled();
    expect(props.onDirty).not.toHaveBeenCalledWith(false);
    expect(props.onBusy).toHaveBeenLastCalledWith(false);
    expect(savePlan).toHaveBeenCalledOnce();
  });

  it("loads character pages explicitly, preserves unavailable selections, and retries a failed page", async () => {
    const firstPage = deferred<CharacterListPageResponse>();
    const listCharacters = vi
      .fn()
      .mockReturnValueOnce(firstPage.promise)
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(
        characterPage({
          items: [
            characterListItem({
              character_id: secondCharacterId,
              name: "访客",
            }),
          ],
        }),
      );
    const savePlan = vi
      .fn()
      .mockImplementation(
        (_project: string, _chapter: string, input: ChapterPlanInput) =>
          Promise.resolve(chapterPlan(input)),
      );
    mount({
      plan: chapterPlan({
        scenes: [scene("one", { character_ids: [secondCharacterId] })],
      }),
      characterClient: characterClient({ listCharacters }),
      client: preparationClient({ savePlan }),
    });
    expect(listCharacters).not.toHaveBeenCalled();
    expect(
      screen.getByText("此场景已关联 1 位人物；读取人物列表后可调整。"),
    ).toBeVisible();
    click("读取可关联人物");
    expect(
      screen.getByRole("button", { name: "正在读取人物…" }),
    ).toBeDisabled();
    await act(async () => {
      firstPage.resolve(
        characterPage({ next_cursor: "page-two", has_more: true }),
      );
      await firstPage.promise;
    });
    fireEvent.click(
      screen.getByRole("checkbox", { name: "场景 1 人物：林砚" }),
    );
    click("读取更多人物");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "已选人物仍保留",
    );
    expect(
      screen.getByRole("checkbox", { name: "场景 1 人物：林砚" }),
    ).toBeChecked();
    click("保存章节规划");
    await waitFor(() =>
      expect(savePlan).toHaveBeenCalledWith(
        structureProjectId,
        chapterId,
        expect.objectContaining({
          scenes: [
            expect.objectContaining({
              character_ids: [secondCharacterId, characterId],
            }),
          ],
        }),
        1,
      ),
    );
    click("读取更多人物");
    await waitFor(() => expect(listCharacters).toHaveBeenCalledTimes(3));
    expect(listCharacters).toHaveBeenNthCalledWith(1, {
      projectId: structureProjectId,
      limit: 100,
    });
    expect(listCharacters).toHaveBeenNthCalledWith(3, {
      projectId: structureProjectId,
      limit: 100,
      cursor: "page-two",
    });
    expect(
      screen.getByRole("checkbox", { name: "场景 1 人物：访客" }),
    ).toBeChecked();
    expect(
      screen.getByRole("checkbox", { name: "场景 1 人物：林砚" }),
    ).toBeChecked();
    expect(
      screen.queryByRole("button", { name: "读取更多人物" }),
    ).not.toBeInTheDocument();
  });

  it("selects immutable rule versions and allows deselection at the eight-version limit", async () => {
    const rules = Array.from({ length: 9 }, (_, index) =>
      ruleRevision({ id: `revision-${index}`, version: index + 1 }),
    );
    const savePlan = vi.fn().mockResolvedValue(chapterPlan());
    mount({
      plan: chapterPlan({
        writing_rule_revision_ids: rules.slice(0, 8).map((rule) => rule.id),
      }),
      rules,
      client: preparationClient({ savePlan }),
    });
    expect(
      screen.getByRole("checkbox", { name: "动作方法 · 版本 9" }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByRole("checkbox", { name: "动作方法 · 版本 2" }),
    );
    expect(
      screen.getByRole("checkbox", { name: "动作方法 · 版本 9" }),
    ).toBeEnabled();
    fireEvent.click(
      screen.getByRole("checkbox", { name: "动作方法 · 版本 9" }),
    );
    click("保存章节规划");
    await waitFor(() =>
      expect(savePlan).toHaveBeenCalledWith(
        structureProjectId,
        chapterId,
        expect.objectContaining({
          writing_rule_revision_ids: [
            "revision-0",
            "revision-2",
            "revision-3",
            "revision-4",
            "revision-5",
            "revision-6",
            "revision-7",
            "revision-8",
          ],
        }),
        1,
      ),
    );
  });

  it("enforces scene, beat and focus limits while allowing removal", () => {
    mount({
      plan: chapterPlan({
        memory_focuses: ["一", "二", "三"],
        scenes: Array.from({ length: 12 }, (_, index) =>
          scene(`scene-${index}`, {
            beats:
              index === 0
                ? Array.from({ length: 12 }, (_, beatIndex) => ({
                    id: `beat-${index}-${beatIndex}`,
                    action: "行动",
                    change: "变化",
                  }))
                : [],
          }),
        ),
      }),
    });
    expect(screen.getByRole("button", { name: "增加章节重点" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "增加场景" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "为场景 1 增加推进点" }),
    ).toBeDisabled();
    click("移除最后一项重点");
    expect(screen.getByRole("button", { name: "增加章节重点" })).toBeEnabled();
    click("删除场景 12");
    expect(screen.getByRole("button", { name: "增加场景" })).toBeEnabled();
    fireEvent.click(
      screen.getAllByRole("button", { name: "删除推进点 12" })[0],
    );
    expect(
      screen.getByRole("button", { name: "为场景 1 增加推进点" }),
    ).toBeEnabled();
  });

  it("limits character links to twenty while allowing an existing selection to be replaced", async () => {
    const characters = Array.from({ length: 21 }, (_, index) =>
      characterListItem({
        character_id: `character-${index}`,
        name: `人物${index}`,
      }),
    );
    const savePlan = vi.fn().mockResolvedValue(chapterPlan());
    mount({
      plan: chapterPlan({
        scenes: [
          scene("one", {
            character_ids: characters
              .slice(0, 20)
              .map((character) => character.character_id),
          }),
        ],
      }),
      characterClient: characterClient({
        listCharacters: vi
          .fn()
          .mockResolvedValue(characterPage({ items: characters })),
      }),
      client: preparationClient({ savePlan }),
    });
    click("读取可关联人物");
    expect(
      await screen.findByRole("checkbox", { name: "场景 1 人物：人物20" }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByRole("checkbox", { name: "场景 1 人物：人物0" }),
    );
    fireEvent.click(
      screen.getByRole("checkbox", { name: "场景 1 人物：人物20" }),
    );
    click("保存章节规划");
    await waitFor(() =>
      expect(savePlan).toHaveBeenCalledWith(
        structureProjectId,
        chapterId,
        expect.objectContaining({
          scenes: [
            expect.objectContaining({
              character_ids: characters
                .slice(1)
                .map((character) => character.character_id),
            }),
          ],
        }),
        1,
      ),
    );
  });

  it.each([199, 20001, 200.5, 0])(
    "rejects invalid target length %s without sending a save",
    (target) => {
      const { props } = mount({ plan: chapterPlan() });
      fireEvent.change(
        screen.getByRole("spinbutton", { name: "本章目标字数" }),
        { target: { value: String(target) } },
      );
      click("保存章节规划");
      expect(screen.getByRole("alert")).toHaveTextContent("200–20000 的整数");
      expect(props.client.savePlan).not.toHaveBeenCalled();
      expect(props.onBusy).not.toHaveBeenCalled();
    },
  );

  it.each([200, 20000])(
    "accepts the valid target boundary %s",
    async (target) => {
      const { props } = mount({
        plan: chapterPlan({ target_characters: target }),
      });
      click("保存章节规划");
      await waitFor(() =>
        expect(props.client.savePlan).toHaveBeenCalledWith(
          structureProjectId,
          chapterId,
          expect.objectContaining({ target_characters: target }),
          1,
        ),
      );
    },
  );

  it("rejects empty and duplicate trimmed focuses, and can recover after editing", async () => {
    const { props } = mount();
    click("保存章节规划");
    expect(screen.getByRole("alert")).toHaveTextContent("不重复的章节重点");
    change("章节重点 1", "停步");
    click("增加章节重点");
    change("章节重点 2", " 停步 ");
    click("保存章节规划");
    expect(props.client.savePlan).not.toHaveBeenCalled();
    change("章节重点 2", "试探");
    click("保存章节规划");
    await waitFor(() => expect(props.onSaved).toHaveBeenCalledOnce());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("synchronously suppresses duplicate saves and informs the parent until completion", async () => {
    const pending = deferred<ChapterPlan>();
    const savePlan = vi.fn().mockReturnValue(pending.promise);
    const { props } = mount({
      plan: chapterPlan(),
      client: preparationClient({ savePlan }),
    });
    const saveButton = screen.getByRole("button", { name: "保存章节规划" });
    act(() => {
      fireEvent.click(saveButton);
      fireEvent.click(saveButton);
    });
    expect(savePlan).toHaveBeenCalledOnce();
    expect(props.onBusy).toHaveBeenCalledExactlyOnceWith(true);
    expect(screen.getByRole("textbox", { name: "章节重点 1" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "正在保存规划…" }),
    ).toBeDisabled();
    await act(async () => {
      pending.resolve(chapterPlan({ version: 2 }));
      await pending.promise;
    });
    expect(props.onBusy).toHaveBeenLastCalledWith(false);
    expect(props.onSaved).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "保存章节规划" })).toBeEnabled();
  });

  it("honors the parent busy lock without discarding the draft", () => {
    const { props, rerender } = mount({ plan: chapterPlan() });
    change("章节重点 1", "本地重点草稿");
    rerender(<ChapterPlanningEditor {...props} disabled />);
    expect(screen.getByRole("textbox", { name: "章节重点 1" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "保存章节规划" })).toBeDisabled();
    click("保存章节规划");
    expect(props.client.savePlan).not.toHaveBeenCalled();
    rerender(<ChapterPlanningEditor {...props} />);
    expect(screen.getByRole("textbox", { name: "章节重点 1" })).toHaveValue(
      "本地重点草稿",
    );
    expect(screen.getByRole("status")).toHaveTextContent("规划未保存");
  });
});
