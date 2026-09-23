import type { AIAnalysis, AIAnswer, AICardResult, Proposal, ProposalInput, ProposalStatus, Quest, Rating, Role, StudentProfile, Task, TaskFields, TaskInput, Team } from "./contracts";

async function request<T>(path: string, options: RequestInit = {}, role?: Role): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      headers: { ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...(role ? { "X-Demo-Role": role } : {}), ...options.headers },
      signal: options.signal ?? AbortSignal.timeout(15000),
      cache: "no-store",
    });
  } catch {
    throw new Error("Не удалось связаться с сервером. Проверьте подключение и повторите попытку.");
  }
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data && typeof data === "object" && "detail" in data ? data.detail : null;
    throw new Error(typeof detail === "string" ? detail : response.status === 422 ? "Проверьте заполнение полей: некоторые значения слишком длинные или имеют неверный формат." : "Не удалось выполнить действие. Повторите попытку.");
  }
  return data as T;
}
export const api = {
  listTasks: (business = false) => request<Task[]>(`/tasks${business ? "?view=business" : ""}`, {}, business ? "business" : undefined),
  getTask: (id: string, business = false) => request<Task>(`/tasks/${encodeURIComponent(id)}${business ? "?view=business" : ""}`, {}, business ? "business" : undefined),
  createTask: (input: TaskInput) => request<Task>("/tasks", { method: "POST", body: JSON.stringify(input) }, "business"),
  updateTask: (id: string, input: TaskInput) => request<Task>(`/tasks/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(input) }, "business"),
  confirmTask: (id: string) => request<Task>(`/tasks/${encodeURIComponent(id)}/confirm`, { method: "POST" }, "business"),
  publishTask: (id: string) => request<Task>(`/tasks/${encodeURIComponent(id)}/publish`, { method: "POST" }, "business"),
  previewRating: (fields: TaskFields) => request<Rating>("/rating/preview", { method: "POST", body: JSON.stringify({ fields }) }),
  analyzeTask: (description: string, fields: TaskFields) => request<AIAnalysis>("/ai/analyze", { method: "POST", body: JSON.stringify({ description, fields }) }, "business"),
  buildTaskCard: (description: string, fields: TaskFields, answers: AIAnswer[]) => request<AICardResult>("/ai/build-card", { method: "POST", body: JSON.stringify({ description, fields, answers }) }, "business"),
  profiles: () => request<StudentProfile[]>("/profiles"),
  teams: () => request<Team[]>("/teams"),
  submitProposal: (taskId: string, input: ProposalInput) => request<Proposal>(`/tasks/${encodeURIComponent(taskId)}/proposals`, { method: "POST", body: JSON.stringify(input) }, "student"),
  uploadProposal: (taskId: string, input: ProposalInput, file: File) => {
    const body = new FormData();
    body.append("proposal", JSON.stringify(input));
    body.append("file", file);
    return request<Proposal>(`/tasks/${encodeURIComponent(taskId)}/proposals/upload`, { method: "POST", body, signal: AbortSignal.timeout(30000) }, "student");
  },
  downloadProposalAttachment: async (proposalId: string, attachmentId: string, role: Role, teamId: string): Promise<Blob> => {
    let response: Response;
    try {
      response = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/attachments/${encodeURIComponent(attachmentId)}${role === "student" ? `?teamId=${encodeURIComponent(teamId)}` : ""}`, { headers: { "X-Demo-Role": role }, cache: "no-store", signal: AbortSignal.timeout(30000) });
    } catch { throw new Error("Не удалось скачать PDF. Проверьте подключение и повторите попытку."); }
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      throw new Error(typeof data?.detail === "string" ? data.detail : "Не удалось скачать PDF. Повторите попытку.");
    }
    return response.blob();
  },
  teamProposals: (teamId: string) => request<Proposal[]>(`/proposals?teamId=${encodeURIComponent(teamId)}`, {}, "student"),
  taskProposals: (taskId: string) => request<Proposal[]>(`/proposals?taskId=${encodeURIComponent(taskId)}`, {}, "business"),
  decideProposal: (id: string, status: ProposalStatus, comment: string) => request<Proposal>(`/proposals/${encodeURIComponent(id)}/decision`, { method: "PUT", body: JSON.stringify({ status, comment }) }, "business"),
  updateSkills: (id: string, skills: string[]) => request<StudentProfile>(`/profiles/${encodeURIComponent(id)}/skills`, { method: "PUT", body: JSON.stringify({ skills }) }, "student"),
  quests: (profileId: string) => request<Quest[]>(`/quests?profileId=${encodeURIComponent(profileId)}`),
  saved: (profileId: string) => request<Task[]>(`/saved?profileId=${encodeURIComponent(profileId)}`),
  decideQuest: (id: string, profileId: string, decision: "saved" | "dismissed") => request<{ ok: boolean }>(`/quests/${encodeURIComponent(id)}/decision`, { method: "POST", body: JSON.stringify({ profileId, decision }) }, "student"),
};
