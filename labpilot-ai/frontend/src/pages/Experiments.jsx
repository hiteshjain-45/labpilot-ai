import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Chip, Empty, ErrorNote, LevelChip, Loading, PageHead, StatusChip } from "../components/ui";
import { useAsync, useTitle } from "../lib/hooks";

export default function Experiments() {
  useTitle("Experiments");
  const { data, error, loading, reload } = useAsync(() => api.experiments(), []);
  const [level, setLevel] = useState("all");
  if (loading && !data) return <Loading label="Loading experiments" />;
  if (error) return <ErrorNote error={error} retry={reload} />;
  const rows = data.filter((e) => level === "all" || e.difficulty === level);
  return (
    <>
      <PageHead title="Experiments" actions={
        <label className="check"><span className="small">Level</span>
          <select value={level} onChange={(e) => setLevel(e.target.value)} style={{ width: "auto" }}>
            <option value="all">All levels</option><option value="beginner">Beginner</option><option value="intermediate">Intermediate</option><option value="advanced">Advanced</option>
          </select>
        </label>}>Each experiment is graded against visible and hidden test cases. A score of 80% or more counts as mastered.</PageHead>
      {rows.length === 0 ? <Empty title="No experiments at this level" /> : (
        <div className="table-wrap"><table className="table">
          <thead><tr><th>No.</th><th>Experiment</th><th>Level</th><th>Skills</th><th className="num">Time</th><th className="num">Attempts</th><th className="num">Best score</th><th>Status</th></tr></thead>
          <tbody>
            {rows.map((e, i) => (
              <tr key={e.id}>
                <td>{i + 1}</td>
                <td className="title-cell"><Link to={`/experiments/${e.id}`}>{e.title}</Link><div className="small muted" style={{ fontWeight: 400, maxWidth: "48ch" }}>{e.objective}</div></td>
                <td><LevelChip level={e.difficulty} /></td>
                <td><div className="chips">{e.skills.map((s) => <Chip key={s}>{s}</Chip>)}</div></td>
                <td className="num nowrap">{e.estimated_minutes} min</td>
                <td className="num">{e.progress.attempts}</td>
                <td className="num">{e.progress.best_percent != null ? `${e.progress.best_percent}%` : "None yet"}</td>
                <td><StatusChip status={e.progress.status} /></td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </>
  );
}
