import { Fragment } from "react";

function inline(text) {
  return text.split(/(`[^`]+`)/g).map((part, i) =>
    part.startsWith("`") && part.endsWith("`") && part.length > 2 ? <code key={i}>{part.slice(1, -1)}</code> : <Fragment key={i}>{part}</Fragment>
  );
}

/** Plain text with paragraphs, "- " bullet lists and `code`. Text is always rendered as text, never as HTML. */
export default function RichText({ text }) {
  const blocks = String(text || "").trim().split(/\n{2,}/);
  return (
    <div className="rich">
      {blocks.map((block, i) => {
        const lines = block.split("\n");
        if (lines.every((l) => l.startsWith("- "))) {
          return <ul key={i}>{lines.map((l, j) => <li key={j}>{inline(l.slice(2))}</li>)}</ul>;
        }
        return <p key={i} style={{ whiteSpace: "pre-line" }}>{inline(block)}</p>;
      })}
    </div>
  );
}
