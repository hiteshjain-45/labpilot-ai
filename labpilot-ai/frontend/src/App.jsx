import { lazy } from "react";
import { Link, Navigate, Outlet, Route, Routes, useLocation, useOutletContext } from "react-router-dom";
import { useAuth } from "./auth";
import Shell from "./components/Shell";
import { Loading } from "./components/ui";
import AuthPage, { homeFor } from "./pages/AuthPage";
import CopilotChat from "./pages/CopilotChat";
import Dashboard from "./pages/Dashboard";
import SkillPassportPage from "./pages/SkillPassportPage";
import Viva from "./pages/Viva";
import WhatIf from "./pages/WhatIf";
import Experiments from "./pages/Experiments";
import Progress from "./pages/Progress";
import ExperimentsAdmin from "./pages/teacher/Experiments";
import Overview from "./pages/teacher/Overview";
import StudentDetail from "./pages/teacher/StudentDetail";
import Students from "./pages/teacher/Students";
import { SubmissionList } from "./pages/teacher/Submissions";

// The code editor is large, so the pages that use it load on demand.
const Workspace = lazy(() => import("./pages/Workspace"));
const ExperimentEditor = lazy(() => import("./pages/teacher/ExperimentEditor"));
const SubmissionDetail = lazy(() => import("./pages/teacher/SubmissionDetail"));

function RequireAuth() {
  const { user, ready } = useAuth();
  const location = useLocation();
  if (!ready) return <div className="main"><Loading label="Signing you in" /></div>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <Shell />;
}

function RequireRole({ role }) {
  const { user } = useAuth();
  const context = useOutletContext(); // hand the shell's context on to the page
  return user.role === role ? <Outlet context={context} /> : <Navigate to={homeFor(user)} replace />;
}

function Home() {
  const { user } = useAuth();
  return <Navigate to={homeFor(user)} replace />;
}

function NotFound() {
  return <div className="stack"><h1>Page not found</h1><p>There is nothing at this address. <Link to="/">Go to your home page</Link>.</p></div>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<AuthPage mode="login" />} />
      <Route path="/register" element={<AuthPage mode="register" />} />
      <Route element={<RequireAuth />}>
        <Route index element={<Home />} />
        <Route element={<RequireRole role="student" />}>
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="experiments" element={<Experiments />} />
          <Route path="experiments/:id" element={<Workspace />} />
          <Route path="copilot" element={<CopilotChat />} />
          <Route path="passport" element={<SkillPassportPage />} />
          <Route path="viva" element={<Viva />} />
          <Route path="what-if" element={<WhatIf />} />
          <Route path="progress" element={<Progress />} />
        </Route>
        <Route element={<RequireRole role="teacher" />}>
          <Route path="teacher" element={<Overview />} />
          <Route path="teacher/students" element={<Students />} />
          <Route path="teacher/students/:id" element={<StudentDetail />} />
          <Route path="teacher/experiments" element={<ExperimentsAdmin />} />
          <Route path="teacher/experiments/new" element={<ExperimentEditor />} />
          <Route path="teacher/experiments/:id" element={<ExperimentEditor />} />
          <Route path="teacher/submissions" element={<SubmissionList />} />
          <Route path="teacher/submissions/:id" element={<SubmissionDetail />} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
