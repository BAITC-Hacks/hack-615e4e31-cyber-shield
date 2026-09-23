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
export type QualityField = { field: string; status: "missing" | "needs_work" | "ready"; message: string; suggestion: string; evidence?: string | null };
export type QualityReport = { version: string; mode: "rules" | "openai"; fields: QualityField[]; eligibleFields: string[]; summary: string; warnings?: string[]; model?: string | null };
export type Rating = { score: number; level: Readiness; breakdown: RatingItem[]; missingFields: string[]; quality?: QualityReport };
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
export type Team = { id: string; sourceId?: string | null; name: string; skills: string[]; technologies: string[]; interests: string[] };
export type ProposalStatus = "submitted" | "accepted" | "rejected";
export type ProposalInput = { teamId: string; idea: string; plan: string[]; durationDays: number; prototypeUrl: string; assumptions: string[] };
export type ProposalAttachment = { id: string; name: string; size: number; mediaType: "application/pdf"; createdAt: string };
export type ProjectCompletion = { confirmedAt: string; summary: string; pointsAwarded: number };
export type Proposal = ProposalInput & {
  id: string; sourceId?: string | null; taskId: string; team: Team;
  prototypeIsPlaceholder: boolean; status: ProposalStatus; decisionComment: string;
  createdAt: string; updatedAt: string; taskTitle: string;
  attachments: ProposalAttachment[];
  completion?: ProjectCompletion | null;
};
export type RewardSlot = "background" | "poster" | "plant" | "lamp";
export type RewardItem = { id: string; name: string; description: string; cost: number; slot: RewardSlot; style: string };
export type RewardTransaction = { id: string; kind: "project_reward" | "purchase"; amount: number; label: string; createdAt: string; proposalId: string | null; itemId: string | null };
export type TeamRewards = { teamId: string; balance: number; totalEarned: number; completedProjects: number; items: RewardItem[]; ownedItemIds: string[]; equipped: Record<RewardSlot, string | null>; history: RewardTransaction[] };
export type Quest = { task: Task; matchedSkills: string[]; matchedInterests: string[]; decision: "saved" | "dismissed" | null };
export type AIMode = "local_stub" | "openai";
export type AIExpandedDescription = { mode: AIMode; description: string; questions: string[]; warnings: string[]; sourceQuotes: string[]; confirmed: false; promptVersion: string };
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
