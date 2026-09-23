import { Link } from "react-router-dom";
import { api } from "../../api";
import { Chip, Empty, ErrorNote, LevelChip, Loading, PageHead } from "../../components/ui";
import { pct } from "../../lib/format";
import { useAsync, useTitle } from "../../lib/hooks";

export default function ExperimentsAdmin() {
  useTitle("Manage experiments");
  const { data, error, loading, reload } = useAsync(() => api.teacher.experiments(), []);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorNote error={error} retry={reload} />;
  return (
    <>
      <PageHead title="Experiments" actions={<Link className="btn btn-primary" to="/teacher/experiments/new">New experiment</Link>}>
        Drafts are hidden from students. An experiment needs at least one test case before it can be published.
      </PageHead>
      {data.length === 0 ? <Empty title="No experiments yet">Create the first one to get students started.</Empty> : (
        <div className="table-wrap"><table className="table">
          <thead><tr><th>Experiment</th><th>Level</th><th>Visibility</th><th className="num">Test cases</th><th className="num">Students</th><th className="num">Average best</th><th className="num">Pass rate</th></tr></thead>
          <tbody>{data.map((e) => (
            <tr key={e.id}>
              <td className="title-cell"><Link to={`/teacher/experiments/${e.id}`}>{e.title}</Link></td>
              <td><LevelChip level={e.difficulty} /></td>
              <td><Chip tone={e.is_published ? "pass" : "warn"}>{e.is_published ? "Published" : "Draft"}</Chip></td>
              <td className="num">{e.test_count} ({e.hidden_test_count} hidden)</td>
              <td className="num">{e.students_attempted}</td>
              <td className="num">{pct(e.average_percent)}</td>
              <td className="num">{e.pass_rate == null ? "Not yet" : `${e.pass_rate}%`}</td>
            </tr>))}</tbody>
        </table></div>
      )}
    </>
  );
}
