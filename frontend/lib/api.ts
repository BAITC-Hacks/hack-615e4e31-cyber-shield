import type { AIAnalysis, AIAnswer, AICardResult, Quest, Rating, Role, StudentProfile, Task, TaskFields, TaskInput } from "./contracts";

async function request<T>(path: string, options: RequestInit = {}, role?: Role): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      headers: { "Content-Type": "application/json", ...(role ? { "X-Demo-Role": role } : {}), ...options.headers },
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
  updateSkills: (id: string, skills: string[]) => request<StudentProfile>(`/profiles/${encodeURIComponent(id)}/skills`, { method: "PUT", body: JSON.stringify({ skills }) }, "student"),
  quests: (profileId: string) => request<Quest[]>(`/quests?profileId=${encodeURIComponent(profileId)}`),
  saved: (profileId: string) => request<Task[]>(`/saved?profileId=${encodeURIComponent(profileId)}`),
  decideQuest: (id: string, profileId: string, decision: "saved" | "dismissed") => request<{ ok: boolean }>(`/quests/${encodeURIComponent(id)}/decision`, { method: "POST", body: JSON.stringify({ profileId, decision }) }, "student"),
};
