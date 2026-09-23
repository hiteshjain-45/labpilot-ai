import { Suspense } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useAsync } from "../lib/hooks";
import { Loading } from "./ui";

const Logo = () => (
  <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
    <rect width="32" height="32" rx="6" fill="#f2b705" />
    <path d="M12 6h8v2h-1v6l6 10a2 2 0 0 1-1.7 3H8.7A2 2 0 0 1 7 24l6-10V8h-1z" fill="#123b33" />
  </svg>
);

const STUDENT_NAV = [["/dashboard", "Dashboard"], ["/experiments", "Experiments"], ["/copilot", "AI Copilot"], ["/passport", "Skill Passport"], ["/viva", "AI Viva"], ["/what-if", "What-If"], ["/progress", "My progress"]];
const TEACHER_NAV = [["/teacher", "Overview", true], ["/teacher/students", "Students"], ["/teacher/experiments", "Experiments"], ["/teacher/submissions", "Submissions"]];

export default function Shell() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const { data: status } = useAsync(() => api.status(), []);
  const nav = user.role === "teacher" ? TEACHER_NAV : STUDENT_NAV;

  return (
    <div className="shell">
      <aside className="rail">
        <NavLink to="/" className="brand"><Logo /> LabPilot AI</NavLink>
        <nav aria-label="Main">
          {nav.map(([to, label, end]) => <NavLink key={to} to={to} end={end}>{label}</NavLink>)}
        </nav>
        <div className="rail-foot">
          {status && (
            <div className="mode-note">
              <b>{status.ai.is_real ? "AI guidance on" : "Rule-based guidance"}</b>
              <br />
              {status.ai.is_real ? `Model: ${status.ai.model}` : "No AI provider is configured, so hints come from built-in rules."}
            </div>
          )}
          <div><div className="who">{user.full_name}</div><div>{user.role === "teacher" ? "Teacher" : user.roll_number || "Student"}</div></div>
          <button className="btn btn-sm" onClick={() => { signOut(); navigate("/login"); }}>Sign out</button>
        </div>
      </aside>
      <main className="main" id="content"><Suspense fallback={<Loading />}><Outlet context={{ status }} /></Suspense></main>
    </div>
  );
}
