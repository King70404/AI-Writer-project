import { useMemo, useState } from "react";

import { diffText, type DiffSegment } from "../candidate-diff";

type View = "compare" | "original" | "candidate";
const VIEWS: readonly { readonly id: View; readonly label: string }[] = [
  { id: "compare", label: "对照" },
  { id: "original", label: "只看原文" },
  { id: "candidate", label: "只看候选" },
];
const TAIL = 120;

function Segments({
  segments,
  side,
}: {
  readonly segments: readonly DiffSegment[];
  readonly side: "original" | "candidate";
}) {
  return (
    <>
      {segments.map((segment, index) => {
        if (segment.type === "equal")
          return <span key={index}>{segment.text}</span>;
        if (segment.type === "delete")
          return side === "original" ? (
            <del key={index} className="candidate-diff__deleted">
              {segment.text}
            </del>
          ) : null;
        return side === "candidate" ? (
          <ins key={index} className="candidate-diff__inserted">
            {segment.text}
          </ins>
        ) : null;
      })}
    </>
  );
}

/**
 * 原文/候选只读对照（B1）。改写显示任务准备时保存的原选区与候选的逐字差异；
 * 续写显示当前正文末尾与将追加的候选。全部在本地计算，不调用模型，
 * 也不写入正文：采用仍需作者点击下方的采用按钮。
 */
export function CandidateComparison({
  operation,
  original,
  candidate,
  currentContent,
}: {
  readonly operation: "continue" | "rewrite";
  /** 改写：任务准备时保存的原选区。续写时忽略。 */
  readonly original: string;
  readonly candidate: string;
  /** 续写：编辑器当前正文，用于展示插入位置。 */
  readonly currentContent: string;
}) {
  const [view, setView] = useState<View>("compare");
  const diff = useMemo(
    () => (operation === "rewrite" ? diffText(original, candidate) : null),
    [operation, original, candidate],
  );
  if (operation === "continue") {
    const tail =
      currentContent.length > TAIL
        ? `…${currentContent.slice(-TAIL)}`
        : currentContent;
    return (
      <section className="candidate-diff" aria-label="候选插入位置">
        <h5>插入位置：正文末尾</h5>
        <p className="candidate-diff__note">
          采用后候选会追加在当前正文之后（另起一段）；采用前正文不会改变。
        </p>
        <div
          className="candidate-diff__pane"
          role="group"
          aria-label="正文末尾与候选"
        >
          {tail ? (
            <span className="candidate-diff__context">{tail}</span>
          ) : (
            <span className="candidate-diff__context">（当前正文为空）</span>
          )}
          {tail ? "\n\n" : null}
          <ins className="candidate-diff__inserted">{candidate}</ins>
        </div>
      </section>
    );
  }
  const summary = diff!.approximate
    ? `差异较大，未逐字标记：整段对照原文 ${diff!.deletedCharacters} 字与候选 ${diff!.insertedCharacters} 字。`
    : `删除 ${diff!.deletedCharacters} 字，新增 ${diff!.insertedCharacters} 字（非空白字符，本地比较）。`;
  return (
    <section className="candidate-diff" aria-label="原文与候选对照">
      <h5>原文与候选对照</h5>
      <p className="candidate-diff__note" role="note">
        {summary}原文为任务准备时保存的选区；采用前正文不会改变。
      </p>
      <div className="candidate-diff__views" role="group" aria-label="对照视图">
        {VIEWS.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-pressed={view === item.id}
            onClick={() => setView(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div
        className={`candidate-diff__columns candidate-diff__columns--${view}`}
      >
        {view !== "candidate" ? (
          <div
            className="candidate-diff__pane"
            role="group"
            aria-label="原文（删除部分划线）"
          >
            <Segments segments={diff!.segments} side="original" />
          </div>
        ) : null}
        {view !== "original" ? (
          <div
            className="candidate-diff__pane"
            role="group"
            aria-label="候选（新增部分标记）"
          >
            <Segments segments={diff!.segments} side="candidate" />
          </div>
        ) : null}
      </div>
    </section>
  );
}
