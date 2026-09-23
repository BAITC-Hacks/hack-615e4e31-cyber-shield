export type Role = "business" | "student";
export type Readiness = "draft" | "workable" | "ready" | "priority";
export type TaskFields = {
  title: string;
  context: string;
  need: string;
  users: string;
  data: string;
  constraints: string;
  expectedResult: string;
  successCriteria: string;
  contact: string;
  interactionFormat: string;
  feedbackProcess: string;
};
export type TaskInput = {
  fields: TaskFields;
  company: string;
  topic: string;
  requiredSkills: string[];
};
export type RatingItem = { key: string; label: string; earned: number; max: number; missing: string[] };
export type Rating = { score: number; level: Readiness; breakdown: RatingItem[]; missingFields: string[] };
export type Task = TaskInput & {
  id: string;
  published: boolean;
  confirmed: boolean;
  hasUnpublishedChanges: boolean;
  rating: Rating;
  previewRating: Rating;
  revision: number;
  publishedRevision: number | null;
  updatedAt: string;
  sourceId?: string | null;
  sourceDraftId?: string | null;
  industry?: string;
  confirmedFields?: string[] | null;
};
export type StudentProfile = { id: string; name: string; course: string; skills: string[]; interests: string[] };
export type Quest = { task: Task; matchedSkills: string[]; matchedInterests: string[]; decision: "saved" | "dismissed" | null };
export type AIMode = "local_stub" | "openai";
export type AIQuestion = { id: string; field: keyof TaskFields; question: string };
export type AIAnswer = { field: keyof TaskFields; answer: string };
export type AIAnalysis = { mode: AIMode; missingFields: string[]; questions: AIQuestion[]; warnings: string[]; promptVersion: string };
export type AISource = { sourceId: string; quote: string };
export type AICardResult = { mode: AIMode; fields: TaskFields; sources: Record<string, AISource[]>; warnings: string[]; confirmed: false; promptVersion: string };
export const TOPICS = ["Все направления", "Торговля", "Образование", "Сервисы", "Логистика", "HoReCa"];
export const SKILLS = ["Python", "SQL", "React", "TypeScript", "Аналитика", "Дизайн", "Figma", "Автоматизация"];
export const LEVELS: Record<Readiness, { label: string; range: string }> = {
  draft: { label: "Нужно уточнить", range: "0–39" },
  workable: { label: "Рабочая", range: "40–69" },
  ready: { label: "Готовая", range: "70–89" },
  priority: { label: "Приоритетная", range: "90–100" },
};
export const EMPTY_FIELDS: TaskFields = { title: "", context: "", need: "", users: "", data: "", constraints: "", expectedResult: "", successCriteria: "", contact: "", interactionFormat: "", feedbackProcess: "" };
