// The API returns naive UTC timestamps; treat them as UTC when parsing.
export function toDate(value) {
  if (!value) return null;
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
}

export function formatDate(value, withTime = true) {
  const d = toDate(value);
  if (!d) return "Never";
  const opts = withTime ? { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" } : { day: "numeric", month: "short" };
  return d.toLocaleString(undefined, opts);
}

export function ago(value) {
  const d = toDate(value);
  if (!d) return "never";
  const s = Math.max(0, (Date.now() - d.getTime()) / 1000);
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  const days = Math.round(s / 86400);
  return days === 1 ? "yesterday" : `${days} days ago`;
}

export const pct = (v) => (v == null ? "Not yet" : `${Math.round(v)}%`);
export const score = (s, max) => `${Number.isInteger(s) ? s : Number(s).toFixed(1)} / ${max}`;
export const LEVELS = { beginner: "Beginner", intermediate: "Intermediate", advanced: "Advanced" };
export const STATUS_TEXT = { not_started: "Not started", in_progress: "In progress", attempted: "Attempted", mastered: "Mastered" };
export const VERDICT = {
  passed: ["Match", "pass"], wrong_answer: ["Mismatch", "fail"], runtime_error: ["Runtime error", "fail"],
  syntax_error: ["Syntax error", "fail"], timeout: ["Timed out", "fail"], output_limit: ["Too much output", "fail"],
};
export const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
