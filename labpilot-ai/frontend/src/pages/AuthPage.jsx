import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { Field, Notice, Spinner } from "../components/ui";
import { useTitle } from "../lib/hooks";

const SHOW_DEMO = import.meta.env.VITE_SHOW_DEMO !== "false";
export const homeFor = (user) => (user.role === "teacher" ? "/teacher" : "/dashboard");

export default function AuthPage({ mode }) {
  const isRegister = mode === "register";
  useTitle(isRegister ? "Create account" : "Sign in");
  const { user, signIn, register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ email: "", password: "", full_name: "", roll_number: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  if (user) return <Navigate to={homeFor(user)} replace />;

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const u = isRegister
        ? await register({ email: form.email, password: form.password, full_name: form.full_name, roll_number: form.roll_number || null })
        : await signIn(form.email, form.password);
      navigate(location.state?.from || homeFor(u), { replace: true });
    } catch (err) { setError(err); } finally { setBusy(false); }
  }

  return (
    <div className="auth">
      <div className="auth-side">
        <div className="brand"><svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="6" fill="#f2b705" /><path d="M12 6h8v2h-1v6l6 10a2 2 0 0 1-1.7 3H8.7A2 2 0 0 1 7 24l6-10V8h-1z" fill="#123b33" /></svg>LabPilot AI</div>
        <div className="stack-lg">
          <h1>Write it, run it, see what to fix.</h1>
          <p>A virtual lab for Python practicals. Your code runs against real test cases, mistakes are explained, and the next experiment is chosen from how you are actually doing.</p>
          <div className="sample" aria-hidden="true">
            <div className="small">Illustration of the observation table, not real data</div>
            <div className="row"><span>Sample: n = 5</span><b style={{ color: "#8fd9ae" }}>Match</b></div>
            <div className="row"><span>Zero</span><b style={{ color: "#8fd9ae" }}>Match</b></div>
            <div className="row"><span>Largest allowed: n = 20</span><b style={{ color: "#ffb3aa" }}>Mismatch</b></div>
          </div>
        </div>
        <span className="small">Software Engineering Lab prototype</span>
      </div>
      <div className="auth-form">
        <h2>{isRegister ? "Create a student account" : "Sign in"}</h2>
        <form onSubmit={submit} noValidate>
          {isRegister && <Field label="Full name" id="name"><input id="name" type="text" autoComplete="name" value={form.full_name} onChange={set("full_name")} required /></Field>}
          <Field label="Email" id="email"><input id="email" type="email" autoComplete="email" value={form.email} onChange={set("email")} required /></Field>
          <Field label="Password" id="password" hint={isRegister ? "At least 8 characters." : null}>
            <input id="password" type="password" autoComplete={isRegister ? "new-password" : "current-password"} value={form.password} onChange={set("password")} required />
          </Field>
          {isRegister && <Field label="Roll number (optional)" id="roll"><input id="roll" type="text" value={form.roll_number} onChange={set("roll_number")} /></Field>}
          {error && <div style={{ marginBottom: 14 }}><Notice tone="error">{error.message}</Notice></div>}
          <div className="actions">
            <button className="btn btn-primary" type="submit" disabled={busy}>{busy && <Spinner />}{isRegister ? "Create account" : "Sign in"}</button>
            {isRegister ? <Link to="/login">I already have an account</Link> : <Link to="/register">Create a student account</Link>}
          </div>
        </form>
        {SHOW_DEMO && !isRegister && (
          <div className="demo">
            <b>Demo accounts</b>
            <span className="muted">Created by the seed script. Teachers cannot self-register.</span>
            <div className="actions">
              <button className="btn btn-sm" type="button" onClick={() => setForm((f) => ({ ...f, email: "student@labpilot.demo", password: "Student@123" }))}>Fill in student login</button>
              <button className="btn btn-sm" type="button" onClick={() => setForm((f) => ({ ...f, email: "teacher@labpilot.demo", password: "Teacher@123" }))}>Fill in teacher login</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
