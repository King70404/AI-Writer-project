import { useMemo } from "react";

import { diffText, type DiffSegment } from "../novel-structure/candidate-diff";

function Side({
  segments,
  side,
}: {
  readonly segments: readonly DiffSegment[];
  readonly side: "left" | "right";
}) {
  return (
    <>
      {segments.map((segment, index) => {
        if (segment.type === "equal")
          return <span key={index}>{segment.text}</span>;
        if (segment.type === "delete")
          return side === "left" ? (
            <del key={index} className="candidate-diff__deleted">
              {segment.text}
            </del>
          ) : null;
        return side === "right" ? (
          <ins key={index} className="candidate-diff__inserted">
            {segment.text}
          </ins>
        ) : null;
      })}
    </>
  );
}

/** 两个正文版本的本地逐字对照；只读，不调用模型，也不写入任何一方。 */
export function VersionComparison({
  label,
  leftLabel,
  rightLabel,
  left,
  right,
}: {
  readonly label: string;
  readonly leftLabel: string;
  readonly rightLabel: string;
  readonly left: string;
  readonly right: string;
}) {
  const diff = useMemo(() => diffText(left, right), [left, right]);
  return (
    <section className="candidate-diff" aria-label={label}>
      <p className="candidate-diff__note">
        {diff.approximate
          ? "差异较大，未逐字标记，以下为两份全文。"
          : `${rightLabel}相对${leftLabel}：删除 ${diff.deletedCharacters} 字，新增 ${diff.insertedCharacters} 字（本地比较）。`}
      </p>
      <div className="candidate-diff__columns candidate-diff__columns--compare">
        <div
          className="candidate-diff__pane"
          role="group"
          aria-label={leftLabel}
        >
          <Side segments={diff.segments} side="left" />
        </div>
        <div
          className="candidate-diff__pane"
          role="group"
          aria-label={rightLabel}
        >
          <Side segments={diff.segments} side="right" />
        </div>
      </div>
    </section>
  );
}
