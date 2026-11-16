import { useEffect, useState } from "react";
import { Link } from "react-router";
import { bookshelfClient, type BookshelfOverviewPage } from "../api/workspace";
import { projectStructurePath } from "../../projects/routing";

export function BookshelfOverview({
  client = bookshelfClient,
}: {
  readonly client?: typeof bookshelfClient;
}) {
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [page, setPage] = useState<BookshelfOverviewPage | null>(null);
  const [error, setError] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [busy, setBusy] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      if (controller.signal.aborted) return;
      void client
        .page(offset, 20, controller.signal)
        .then((result) => {
          if (!controller.signal.aborted) {
            setPage(result);
            setUnavailable(result === null);
            setError(false);
          }
        })
        .catch(() => {
          if (!controller.signal.aborted) setError(true);
        })
        .finally(() => {
          if (!controller.signal.aborted) setBusy(false);
        });
    });
    return () => controller.abort();
  }, [client, offset, attempt]);
  const load = (next: number) => {
    setBusy(true);
    setError(false);
    setUnavailable(false);
    setOffset(next);
    setAttempt((value) => value + 1);
  };
  return (
    <section aria-label="全书架汇总">
      <h3>全书架汇总</h3>
      <button type="button" disabled={busy} onClick={() => load(offset)}>
        刷新书架汇总
      </button>
      {busy ? (
        <p role="status">正在读取书架汇总…</p>
      ) : error ? (
        <p role="alert">书架汇总读取失败，请重试。</p>
      ) : unavailable ? (
        <p>书架汇总暂不可用。</p>
      ) : page ? (
        <>
          {page.items.length === 0 ? (
            <p>书架暂无小说。</p>
          ) : (
            <>
              <p>字数按已保存正文的非空白字符统计；候选与规划不计入。</p>
              <table>
                <caption>
                  共 {page.total} 本小说，当前第 {Math.floor(offset / 20) + 1}{" "}
                  页
                </caption>
                <thead>
                  <tr>
                    <th>小说</th>
                    <th>字数</th>
                    <th>卷数</th>
                    <th>章数</th>
                    <th>草稿</th>
                    <th>待检查</th>
                    <th>定稿</th>
                    <th>待办</th>
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((book) => (
                    <tr key={book.project_id}>
                      <th>
                        <Link to={projectStructurePath(book.project_id)}>
                          {book.title}
                        </Link>
                      </th>
                      <td>{book.characters}</td>
                      <td>{book.volume_count}</td>
                      <td>{book.chapter_count}</td>
                      <td>{book.editorial.draft}</td>
                      <td>{book.editorial.review}</td>
                      <td>{book.editorial.final}</td>
                      <td>{book.action_total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => load(Math.max(0, offset - 20))}
          >
            汇总上一页
          </button>
          <button
            type="button"
            disabled={page.next_offset === null}
            onClick={() => load(page.next_offset ?? offset)}
          >
            汇总下一页
          </button>
        </>
      ) : null}
    </section>
  );
}
