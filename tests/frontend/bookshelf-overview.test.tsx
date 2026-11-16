import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { StrictMode } from "react";
import { MemoryRouter } from "react-router";
import { expect, it, vi } from "vitest";
import { BookshelfOverview } from "../../frontend/src/features/workbench/components/BookshelfOverview";
import {
  parseBookshelfOverview,
  type BookshelfOverviewPage,
} from "../../frontend/src/features/workbench/api/workspace";

const book = {
  project_id: "prj_01M6V54EP9HX6PH6P0N6J50QC5",
  title: "风雨",
  characters: 1234,
  chapter_count: 3,
  volume_count: 1,
  editorial: { draft: 1, review: 1, final: 1 },
  action_total: 2,
};
const page: BookshelfOverviewPage = {
  total: 21,
  offset: 0,
  limit: 20,
  next_offset: 20,
  items: [book],
  generated_at: "now",
};
it("renders real per-book counts from one page request and loads the next page explicitly", async () => {
  const read = vi
    .fn()
    .mockResolvedValueOnce(page)
    .mockResolvedValueOnce({ ...page, offset: 20, next_offset: null });
  render(
    <MemoryRouter>
      <BookshelfOverview client={{ page: read }} />
    </MemoryRouter>,
  );
  const table = await screen.findByRole("table");
  expect(within(table).getByRole("link", { name: "风雨" })).toHaveAttribute(
    "href",
    "/projects/prj_01M6V54EP9HX6PH6P0N6J50QC5/structure",
  );
  expect(within(table).getByText("1234")).toBeVisible();
  expect(read).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "汇总下一页" }));
  await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
  expect(read.mock.calls[1][0]).toBe(20);
  expect(
    await screen.findByRole("button", { name: "汇总下一页" }),
  ).toBeDisabled();
});
it("shows an empty state and recovers from a failed page request", async () => {
  const read = vi
    .fn()
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ ...page, total: 0, items: [], next_offset: null });
  render(
    <MemoryRouter>
      <BookshelfOverview client={{ page: read }} />
    </MemoryRouter>,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("读取失败");
  fireEvent.click(screen.getByRole("button", { name: "刷新书架汇总" }));
  expect(await screen.findByText("书架暂无小说。")).toBeVisible();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});
it("validates statistics and page bounds while omitting unrequested data", () => {
  const valid = {
    ...page,
    next_offset: 1,
    items: [{ ...book, content: "must not escape" }],
  };
  expect(JSON.stringify(parseBookshelfOverview(valid))).not.toContain(
    "must not escape",
  );
  expect(() => parseBookshelfOverview({ ...valid, limit: 101 })).toThrow();
  expect(() =>
    parseBookshelfOverview({ ...valid, items: [{ ...book, characters: -1 }] }),
  ).toThrow();
  expect(() => parseBookshelfOverview({ ...valid, next_offset: 10 })).toThrow();
});

it("reports unavailable statistics without presenting an empty bookshelf", async () => {
  render(
    <MemoryRouter>
      <BookshelfOverview client={{ page: vi.fn().mockResolvedValue(null) }} />
    </MemoryRouter>,
  );
  expect(await screen.findByText("书架汇总暂不可用。")).toBeVisible();
  expect(screen.queryByText("书架暂无小说。")).not.toBeInTheDocument();
});

it("does not send a cancelled duplicate request during strict-mode mounting", async () => {
  const read = vi.fn().mockResolvedValue(page);
  render(
    <StrictMode>
      <MemoryRouter>
        <BookshelfOverview client={{ page: read }} />
      </MemoryRouter>
    </StrictMode>,
  );
  await screen.findByRole("table");
  expect(read).toHaveBeenCalledTimes(1);
  const signal: unknown = read.mock.calls[0][2];
  expect(signal).toBeInstanceOf(AbortSignal);
  expect((signal as AbortSignal).aborted).toBe(false);
});
