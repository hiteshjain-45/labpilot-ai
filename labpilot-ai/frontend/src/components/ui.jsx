import { LEVELS, STATUS_TEXT } from "../lib/format";

export const Spinner = () => <span className="spinner" aria-hidden="true" />;

export function Loading({ label = "Loading" }) {
  return <p className="empty" role="status"><Spinner /> {label}</p>;
}

export function Notice({ tone = "info", children, role }) {
  return <div className={`notice ${tone === "info" ? "" : tone}`} role={role || (tone === "error" ? "alert" : "status")}>{children}</div>;
}

export function ErrorNote({ error, retry }) {
  if (!error) return null;
  return (
    <Notice tone="error">
      {error.message || "Something went wrong."}{" "}
      {retry && <button className="btn-link" onClick={retry}>Try again</button>}
    </Notice>
  );
}

export function Empty({ title, children }) {
  return <div className="empty"><strong>{title}</strong>{children}</div>;
}

export const Chip = ({ tone = "", children, title }) => <span className={`chip ${tone}`} title={title}>{children}</span>;

export const LevelChip = ({ level }) => <Chip tone={level === "advanced" ? "solid" : level === "intermediate" ? "info" : ""}>{LEVELS[level] || level}</Chip>;

export function StatusChip({ status }) {
  const tone = status === "mastered" ? "pass" : status === "attempted" ? "warn" : status === "in_progress" ? "info" : "";
  return <Chip tone={tone}>{STATUS_TEXT[status] || status}</Chip>;
}

export function PageHead({ title, children, actions }) {
  return (
    <div className="page-head">
      <div><h1>{title}</h1>{children && <p className="muted">{children}</p>}</div>
      {actions && <div className="actions">{actions}</div>}
    </div>
  );
}

export function Section({ title, aside, children }) {
  return (
    <section className="section">
      {(title || aside) && <header>{title && <h2>{title}</h2>}{aside && <div className="small muted">{aside}</div>}</header>}
      {children}
    </section>
  );
}

export function Field({ label, hint, children, id }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}

export function Busy({ busy, children }) {
  return <>{busy && <Spinner />}{children}</>;
}
