// Thin client for the LabPilot API. Every endpoint the UI uses is listed here.
const BASE = import.meta.env.VITE_API_URL || "";
const TOKEN_KEY = "labpilot.token";

let unauthorizedHandler = () => {};
export const onUnauthorized = (fn) => { unauthorizedHandler = fn; };
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (token) => (token ? localStorage.setItem(TOKEN_KEY, token) : localStorage.removeItem(TOKEN_KEY));

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function request(method, path, body) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(BASE + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check that the backend is running on port 8000.");
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && token && !path.startsWith("/api/auth/login")) unauthorizedHandler();
    const detail = data && data.detail;
    throw new ApiError(res.status, typeof detail === "string" ? detail : `The request failed (${res.status}).`);
  }
  return data;
}

const get = (path) => request("GET", path);
const post = (path, body = {}) => request("POST", path, body);
const put = (path, body = {}) => request("PUT", path, body);
const patch = (path, body) => request("PATCH", path, body);
const del = (path) => request("DELETE", path);
const query = (params) => {
  const q = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => v !== "" && v != null && q.set(k, v));
  const s = q.toString();
  return s ? `?${s}` : "";
};

const experimentParams = (experimentId) => ({ experiment_id: experimentId });
const sessionParams = (sessionId) => ({ session_id: sessionId });

export const api = {
  // auth & profile
  login: (email, password) => post("/api/auth/login", { email, password }),
  register: (body) => post("/api/auth/register", body),
  me: () => get("/api/auth/me"),
  updateProfile: (full_name) => patch("/api/users/me", { full_name }),
  changePassword: (current_password, new_password) => post("/api/users/me/password", { current_password, new_password }),
  status: () => get("/api/system/status"),
  taxonomy: () => get("/api/system/taxonomy"),

  // student
  dashboard: () => get("/api/students/me/dashboard"),
  experiments: () => get("/api/experiments"),
  experiment: (id) => get(`/api/experiments/${id}`),
  run: (id, code) => post(`/api/experiments/${id}/run`, { code }),
  submit: (id, code) => post(`/api/experiments/${id}/submit`, { code }),
  history: (id) => get(`/api/experiments/${id}/submissions`),
  submission: (id) => get(`/api/submissions/${id}`),
  hint: (id, body) => post(`/api/experiments/${id}/copilot/hint`, body),
  hintHistory: (id) => get(`/api/experiments/${id}/copilot/history`),
  copilotContext: (experimentId) => get(`/api/copilot/context${query(experimentParams(experimentId))}`),
  copilotMessages: (experimentId) => get(`/api/copilot/messages${query(experimentParams(experimentId))}`),
  copilotSend: (body) => post("/api/copilot/messages", body),

  whatIf: (id) => get(`/api/experiments/${id}/whatif`),
  whatIfConditions: (id) => get(`/api/experiments/${id}/whatif/explore`),
  exploreWhatIf: (id, body) => post(`/api/experiments/${id}/whatif/explore`, body),
  runWhatIf: (id, body) => post(`/api/experiments/${id}/whatif/run`, body),
  mistakes: () => get("/api/mistakes/me"),
  skills: () => get("/api/skills/me"),
  skillPassport: () => get("/api/skills/me/passport"),
  vivaContext: () => get("/api/viva/context"),
  vivaStart: (body) => post("/api/viva/start", body),
  vivaAnswer: (body) => post("/api/viva/answer", body),
  vivaSummary: (sessionId) => get(`/api/viva/summary${query(sessionParams(sessionId))}`),
  recommendation: () => get("/api/recommendations/me"),
  recommendationHistory: () => get("/api/recommendations/me/history"),
  refreshRecommendation: () => post("/api/recommendations/me/refresh"),

  // teacher
  teacher: {
    reviewSubmission: (id, body) => put(`/api/teacher/submissions/${id}/review`, body),
    overview: () => get("/api/teacher/overview"),
    students: () => get("/api/teacher/students"),
    student: (id) => get(`/api/teacher/students/${id}`),
    experiments: () => get("/api/teacher/experiments"),
    experiment: (id) => get(`/api/teacher/experiments/${id}`),
    createExperiment: (body) => post("/api/teacher/experiments", body),
    updateExperiment: (id, body) => patch(`/api/teacher/experiments/${id}`, body),
    deleteExperiment: (id) => del(`/api/teacher/experiments/${id}`),
    validate: (id) => post(`/api/teacher/experiments/${id}/validate`),
    addTest: (id, body) => post(`/api/teacher/experiments/${id}/test-cases`, body),
    updateTest: (id, testId, body) => patch(`/api/teacher/experiments/${id}/test-cases/${testId}`, body),
    deleteTest: (id, testId) => del(`/api/teacher/experiments/${id}/test-cases/${testId}`),
    submissions: (params) => get(`/api/teacher/submissions${query(params)}`),
    submission: (id) => get(`/api/teacher/submissions/${id}`),
  },
};
