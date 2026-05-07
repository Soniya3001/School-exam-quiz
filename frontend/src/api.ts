const BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";

async function request<T = any>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}/api${path}`, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const text = await res.text();
  let data: any = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const detail = (data && (data.detail || data.message)) || text || `Error ${res.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data as T;
}

export const api = {
  get: <T = any>(p: string) => request<T>(p),
  post: <T = any>(p: string, body: any) => request<T>(p, { method: "POST", body: JSON.stringify(body) }),
  put: <T = any>(p: string, body: any) => request<T>(p, { method: "PUT", body: JSON.stringify(body) }),
  del: <T = any>(p: string) => request<T>(p, { method: "DELETE" }),
};

export const Api = {
  // Admin
  adminLogin: (password: string) => api.post("/admin/login", { password }),
  adminPassword: (new_password: string) => api.post("/admin/password", { new_password }),
  listTeachers: () => api.get("/admin/teachers"),
  pendingTeachers: () => api.get("/admin/pending-teachers"),
  approveTeacher: (tid: string) => api.post(`/admin/teachers/${tid}/approve`, {}),
  rejectTeacher: (tid: string) => api.post(`/admin/teachers/${tid}/reject`, {}),
  createTeacher: (b: { name: string; subject: string; password: string; school_id?: string }) =>
    api.post("/admin/teachers", b),
  updateTeacher: (tid: string, b: { name: string; subject: string; password: string }) =>
    api.put(`/admin/teachers/${tid}`, b),
  toggleTeacher: (tid: string) => api.post(`/admin/teachers/${tid}/toggle`, {}),
  deleteTeacher: (tid: string) => api.del(`/admin/teachers/${tid}`),
  clearTeacherData: (tid: string) => api.del(`/admin/teachers/${tid}/data`),
  adminStudents: () => api.get("/admin/students"),
  deleteStudent: (key: string) => api.del(`/admin/students/${encodeURIComponent(key)}`),
  clearAll: () => api.post("/admin/clear-all", {}),

  // Teacher
  teacherRegister: (b: { name: string; subject: string; password: string; school_id: string }) =>
    api.post("/teacher/register", b),
  teacherPublicList: () => api.get("/teacher/public-list"),
  teacherLogin: (teacher_id: string, password: string, school_id?: string) =>
    api.post("/teacher/login", { teacher_id, password, school_id: school_id || "" }),
  teacherState: (tid: string) => api.get(`/teacher/${tid}/state`),
  teacherGenerate: (b: {
    teacher_id: string; lesson_text?: string; image_base64?: string;
    count: number; test_class: string; subject: string;
    language?: string; difficulty?: number; test_type?: string;
  }) => api.post("/teacher/generate", b),
  teacherActivate: (teacher_id: string, join_code: string) =>
    api.post("/teacher/activate", { teacher_id, join_code }),
  teacherReveal: (tid: string, test_class: string) =>
    api.post(`/teacher/${tid}/reveal/${encodeURIComponent(test_class.replace(/ /g, "_"))}`, {}),
  teacherHistory: (tid: string) => api.get(`/teacher/${tid}/history`),
  gradeSubjective: (b: { teacher_id: string; join_code: string; student_name: string; marks: Record<string, number> }) =>
    api.post("/teacher/grade-subjective", b),

  // Student
  findTest: (b: { join_code: string; student_name: string; student_class: string; school_id?: string }) =>
    api.post("/student/find-test", b),
  submit: (b: {
    student_name: string; student_class: string; student_subject: string;
    join_code: string; answers: Record<string, any>; auto_submit?: boolean;
  }) => api.post("/student/submit", b),
  studentHistory: (name: string, student_class: string) =>
    api.get(`/student/history?name=${encodeURIComponent(name)}&student_class=${encodeURIComponent(student_class)}`),
};
