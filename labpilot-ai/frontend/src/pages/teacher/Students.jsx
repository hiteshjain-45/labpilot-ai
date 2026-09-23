import { Link } from "react-router-dom";
import { api } from "../../api";
import { Empty, ErrorNote, Loading, PageHead } from "../../components/ui";
import { ago, pct } from "../../lib/format";
import { useAsync, useTitle } from "../../lib/hooks";

export default function Students() {
  useTitle("Students");
  const { data, error, loading, reload } = useAsync(() => api.teacher.students(), []);
  if (loading && !data) return <Loading label="Loading students" />;
  if (error) return <ErrorNote error={error} retry={reload} />;
  return (
    <>
      <PageHead title="Students">A low first-attempt score with a high best score means a student got there, but needed several tries.</PageHead>
      {data.length === 0 ? <Empty title="No students yet">Students create their own accounts on the sign-in page.</Empty> : (
        <div className="table-wrap"><table className="table">
          <thead><tr><th>Name</th><th>Roll number</th><th className="num">Submitted</th><th className="num">Mastered</th><th className="num">Best score</th><th className="num">First attempt</th><th className="num">Graded</th><th>Last active</th></tr></thead>
          <tbody>
            {data.map((s) => (
              <tr key={s.id}>
                <td className="title-cell"><Link to={`/teacher/students/${s.id}`}>{s.full_name}</Link><div className="small muted" style={{ fontWeight: 400 }}>{s.email}</div></td>
                <td>{s.roll_number || "None"}</td>
                <td className="num">{s.experiments_submitted}</td>
                <td className="num">{s.experiments_mastered}</td>
                <td className="num">{pct(s.average_percent)}</td>
                <td className="num">{pct(s.first_attempt_percent)}</td>
                <td className="num">{s.graded_submissions}</td>
                <td className="nowrap">{s.last_active ? ago(s.last_active) : "Never"}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </>
  );
}
