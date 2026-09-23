import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../api";
import CodeEditor from "../../components/CodeEditor";
import Observations from "../../components/Observations";
import { Chip, ErrorNote, Loading, PageHead, Spinner } from "../../components/ui";
import { ago, formatDate, score } from "../../lib/format";
import { useAsync, useTitle } from "../../lib/hooks";

const tone = (s) => (s === "passed" ? "pass" : s === "partial" ? "warn" : "fail");

function ReviewForm({ submissionId, review, onSaved }) {
  const [status, setStatus] = useState(review?.status || "approved");
  const [remark, setRemark] = useState(review?.remark || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);

  async function save() {
    setBusy(true); setError(null);
    try {
      await api.teacher.reviewSubmission(submissionId, { status, remark });
      setSaved(true);
      onSaved?.();
    } catch (e) { setError(e); } finally { setBusy(false); }
  }

  return (
    <div>
      <h2 style={{ marginBottom: 8 }}>Your review</h2>
      <div className="stack">
        {review && (
          <p className="small muted">
            Last reviewed by {review.teacher_name}, {ago(review.reviewed_at)}. The student sees this beside their submission.
          </p>
        )}
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor="review-status">Outcome</label>
          <select id="review-status" value={status} disabled={busy} onChange={(e) => { setStatus(e.target.value); setSaved(false); }}>
            <option value="approved">Approved</option>
            <option value="needs_rework">Needs rework</option>
          </select>
        </div>
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor="review-remark">Remark for the student</label>
          <textarea id="review-remark" rows={3} maxLength={2000} value={remark} disabled={busy}
            onChange={(e) => { setRemark(e.target.value); setSaved(false); }} placeholder="What to fix, or what was done well." />
        </div>
        {error && <ErrorNote error={error} />}
        <div className="chips">
          <button className="btn btn-primary" onClick={save} disabled={busy}>{busy && <Spinner />}{review ? "Update review" : "Save review"}</button>
          {saved && <Chip tone="pass">Saved</Chip>}
        </div>
        <p className="small muted">A review never changes the score: grading stays automatic.</p>
      </div>
    </div>
  );
}

export default function SubmissionDetail() {
  const { id } = useParams();
  const { data, error, loading, reload } = useAsync(() => api.teacher.submission(id), [id]);
  useTitle("Submission review");
  if (loading && !data) return <Loading />;
  if (error) return <div className="stack"><ErrorNote error={error} retry={reload} /><Link to="/teacher/submissions">Back to submissions</Link></div>;
  return (
    <>
      <PageHead title={data.experiment_title} actions={<Link className="btn" to="/teacher/submissions">All submissions</Link>}>
        {data.student_name}{data.roll_number ? `, ${data.roll_number}` : ""}. {data.kind === "submit" ? "Graded" : "Practice run"} on {formatDate(data.created_at)}.
      </PageHead>
      <div className="chips" style={{ marginBottom: 20 }}>
        <Chip tone={tone(data.status)}>{data.passed_count} of {data.total_count} cases pass</Chip>
        <Chip>Score {score(data.score, data.max_score)}</Chip>
        {data.attempt && <Chip>Attempt {data.attempt.attempt_number}</Chip>}
        {data.attempt && <Chip>{data.attempt.hints_used} hints used</Chip>}
      </div>
      <div className="stack-lg">
        <ReviewForm submissionId={data.id} review={data.review} onSaved={reload} />
        <div><h2 style={{ marginBottom: 8 }}>Submitted code</h2><CodeEditor value={data.code} readOnly minHeight="160px" /></div>
        <div><h2 style={{ marginBottom: 8 }}>Observations</h2><Observations results={data.results} reveal /></div>
      </div>
    </>
  );
}
