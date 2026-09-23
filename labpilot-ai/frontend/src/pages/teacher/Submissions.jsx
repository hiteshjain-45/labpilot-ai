import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { Chip, Empty, ErrorNote, Loading, PageHead } from "../../components/ui";
import { ago, score } from "../../lib/format";
import { useAsync, useTitle } from "../../lib/hooks";

const tone = (s) => (s === "passed" ? "pass" : s === "partial" ? "warn" : "fail");
const PAGE = 25;

export function SubmissionList() {
  useTitle("Submissions");
  const [filters, setFilters] = useState({ experiment_id: "", status: "", kind: "submit" });
  const [offset, setOffset] = useState(0);
  const exps = useAsync(() => api.teacher.experiments(), []);
  const { data, error, loading, reload } = useAsync(() => api.teacher.submissions({ ...filters, limit: PAGE, offset }), [filters, offset]);
  const set = (k) => (e) => { setOffset(0); setFilters((f) => ({ ...f, [k]: e.target.value })); };
  return (
    <>
      <PageHead title="Submissions">Open any submission to read the code and see every test result, including hidden cases.</PageHead>
      <div className="actions" style={{ marginBottom: 16 }}>
        <label className="check"><span className="small">Experiment</span>
          <select value={filters.experiment_id} onChange={set("experiment_id")} style={{ width: "auto" }}><option value="">All</option>{(exps.data || []).map((e) => <option key={e.id} value={e.id}>{e.title}</option>)}</select></label>
        <label className="check"><span className="small">Outcome</span>
          <select value={filters.status} onChange={set("status")} style={{ width: "auto" }}><option value="">Any</option><option value="passed">All cases pass</option><option value="partial">Some pass</option><option value="failed">None pass</option></select></label>
        <label className="check"><span className="small">Type</span>
          <select value={filters.kind} onChange={set("kind")} style={{ width: "auto" }}><option value="submit">Graded</option><option value="run">Practice runs</option></select></label>
      </div>
      {loading && !data ? <Loading /> : error ? <ErrorNote error={error} retry={reload} /> : data.items.length === 0 ? <Empty title="No submissions match these filters" /> : (
        <>
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Student</th><th>Experiment</th><th>Cases</th><th className="num">Score</th><th>When</th><th><span className="sr-only">Open</span></th></tr></thead>
            <tbody>{data.items.map((s) => (
              <tr key={s.id}>
                <td className="title-cell">{s.student_name}<div className="small muted" style={{ fontWeight: 400 }}>{s.roll_number}</div></td>
                <td>{s.experiment_title}</td>
                <td><Chip tone={tone(s.status)}>{s.passed_count}/{s.total_count}</Chip></td>
                <td className="num">{score(s.score, s.max_score)}</td><td className="nowrap">{ago(s.created_at)}</td>
                <td><Link to={`/teacher/submissions/${s.id}`}>Review</Link></td>
              </tr>))}</tbody>
          </table></div>
          <div className="between" style={{ marginTop: 14 }}>
            <span className="small muted">Showing {offset + 1} to {Math.min(offset + PAGE, data.total)} of {data.total}</span>
            <div className="actions">
              <button className="btn btn-sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
              <button className="btn btn-sm" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
            </div>
          </div>
        </>
      )}
    </>
  );
}
