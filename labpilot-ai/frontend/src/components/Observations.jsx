import { Fragment, useState } from "react";
import { Chip } from "./ui";
import { VERDICT } from "../lib/format";

const preview = (text, lines = 3) => {
  const all = String(text ?? "").replace(/\n+$/, "").split("\n");
  return all.length > lines ? `${all.slice(0, lines).join("\n")}\n...` : all.join("\n");
};

function Lines({ text, other }) {
  const mine = String(text ?? "").replace(/\n+$/, "").split("\n");
  const theirs = String(other ?? "").replace(/\n+$/, "").split("\n");
  return (
    <pre className="code-block">
      {mine.map((line, i) => <div key={i}>{line !== (theirs[i] ?? undefined) && other != null ? <span className="diff">{line || " "}</span> : line || " "}</div>)}
    </pre>
  );
}

function Detail({ r, reveal }) {
  if (r.is_hidden && !reveal) {
    return <p className="small">This is a hidden case. Only the verdict is shown so the input and expected output stay secret until you have solved it.{r.error_type ? ` Error type: ${r.error_type}.` : ""}</p>;
  }
  return (
    <div className="detail-grid">
      <div className="io"><span className="label">Input</span><pre className="code-block">{r.stdin || "(empty)"}</pre></div>
      <div className="io"><span className="label">Expected output</span><Lines text={r.expected_output} /></div>
      <div className="io"><span className="label">Your output</span>{r.actual_output ? <Lines text={r.actual_output} other={r.expected_output} /> : <pre className="code-block">(nothing printed)</pre>}</div>
      {r.stderr && <div className="io" style={{ gridColumn: "1 / -1" }}><span className="label">Error output</span><pre className="code-block err">{r.stderr}</pre></div>}
    </div>
  );
}

export default function Observations({ results, reveal = false }) {
  const [open, setOpen] = useState(() => {
    const first = results.find((r) => !r.passed && (reveal || !r.is_hidden));
    return first ? first.id : null;
  });
  return (
    <div className="table-wrap">
      <table className="table obs">
        <caption className="sr-only">Test observations</caption>
        <thead><tr><th>No.</th><th>Case</th><th>Input</th><th>Expected</th><th>Observed</th><th>Verdict</th><th><span className="sr-only">Details</span></th></tr></thead>
        <tbody>
          {results.map((r, i) => {
            const [label, tone] = VERDICT[r.status] || [r.status, "fail"];
            const error = ["runtime_error", "syntax_error", "timeout", "output_limit"].includes(r.status);
            return (
              <Fragment key={r.id}>
                <tr>
                  <td>{i + 1}</td>
                  <td><b>{r.name}</b><div className="chips">{r.kind !== "normal" && <Chip>{r.kind === "edge" ? "Edge case" : "Performance"}</Chip>}{reveal && r.is_hidden && <Chip>Hidden from students</Chip>}</div></td>
                  <td>{r.is_hidden && !reveal ? <span className="muted">Hidden</span> : <pre>{preview(r.stdin) || "(empty)"}</pre>}</td>
                  <td>{r.is_hidden && !reveal ? <span className="muted">Hidden</span> : <pre>{preview(r.expected_output)}</pre>}</td>
                  <td>{r.is_hidden && !reveal ? <span className="muted">Hidden</span> : error ? <span className="muted">{r.error_type || label}</span> : <pre>{preview(r.actual_output) || "(nothing)"}</pre>}</td>
                  <td><Chip tone={tone}>{label}</Chip></td>
                  <td><button className="btn-link" aria-expanded={open === r.id} onClick={() => setOpen(open === r.id ? null : r.id)}>{open === r.id ? "Hide" : "Details"}</button></td>
                </tr>
                {open === r.id && <tr className="detail"><td colSpan={7}><Detail r={r} reveal={reveal} /></td></tr>}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
