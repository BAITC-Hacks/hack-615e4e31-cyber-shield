"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Bookmark, Check, FileCheck2, Loader2, Pencil, Send, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { Role, Task, TaskFields } from "@/lib/contracts";
import RatingPanel, { FIELD_LABELS } from "./RatingPanel";
import ProposalForm from "@/components/proposals/ProposalForm";

type Props = {
  task: Task | null; role: Role; saved: boolean; onClose: () => void;
  onEdit: (task: Task) => void; onSave: (task: Task) => Promise<void>;
  teamId: string; onTeamChange: (id: string) => void; onViewProposals: (taskId: string) => void;
  onDirtyChange: (dirty: boolean) => void; onBusyChange: (busy: boolean) => void;
  onProposalSubmitted: () => void;
};
const GROUPS: { title: string; fields: (keyof TaskFields)[] }[] = [
  { title: "О задаче", fields: ["context", "need"] },
  { title: "Аудитория и материалы", fields: ["users", "data"] },
  { title: "Результат и критерии", fields: ["expectedResult", "successCriteria"] },
  { title: "Условия и связь", fields: ["constraints", "contact", "interactionFormat", "feedbackProcess"] },
];

export default function TaskDetails(props: Props) {
  return <TaskDetailsSheet key={props.task?.id ?? "closed"} {...props} />;
}

function TaskDetailsSheet({ task, role, saved, onClose, onEdit, onSave, teamId, onTeamChange, onViewProposals, onDirtyChange, onBusyChange, onProposalSubmitted }: Props) {
  const [proposalOpen, setProposalOpen] = useState(false);
  const [proposalStarted, setProposalStarted] = useState(false);
  const [proposalBusy, setProposalBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);
  const savingLock = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  async function saveTask() {
    if (!task || savingLock.current || saved || savedId === task.id) return;
    const selectedTask = task;
    savingLock.current = true;
    setSaving(true);
    onBusyChange(true);
    setError(null);
    try {
      await onSave(selectedTask);
      if (mounted.current) setSavedId(selectedTask.id);
    } catch (cause) {
      if (mounted.current) setError(cause instanceof Error ? cause.message : "Не удалось сохранить задачу. Попробуйте ещё раз.");
    } finally {
      savingLock.current = false;
      if (mounted.current) { setSaving(false); onBusyChange(false); }
    }
  }

  const isSaved = saved || (!!task && savedId === task.id);
  return <Sheet open={!!task} onOpenChange={(open) => { if (!open) onClose(); }}>
    <SheetContent className="ha-task-details" showCloseButton={false}>
      {task && <>
        <Button variant="ghost" size="icon" onClick={onClose} disabled={saving || proposalBusy} className="ha-task-details-close" aria-label="Закрыть карточку"><X size={20} /></Button>
        <SheetHeader className="ha-task-details-header">
          <div className="ha-task-eyebrow">{task.topic || "Без направления"}</div>
          <SheetTitle>{task.fields.title || "Задача без названия"}</SheetTitle>
          <SheetDescription>{task.company || "Компания не указана"} · {task.published ? "Опубликована" : "Черновик"}</SheetDescription>
          {!!task.requiredSkills.length && <div className="ha-task-skills">{task.requiredSkills.map((skill) => <span className="ha-task-skill-label" key={skill}>{skill}</span>)}</div>}
        </SheetHeader>
        <div className="ha-task-details-body">
          {proposalOpen && <Button type="button" variant="ghost" onClick={() => setProposalOpen(false)} disabled={proposalBusy}><ArrowLeft size={16} />К описанию задачи</Button>}
          {proposalStarted && <div hidden={!proposalOpen}><ProposalForm task={task} teamId={teamId} onTeamChange={onTeamChange} onDirtyChange={onDirtyChange} onBusyChange={(value) => { setProposalBusy(value); onBusyChange(value); }} onSubmitted={onProposalSubmitted} /></div>}
          <div hidden={proposalOpen} className="alem-task-description-sections">
          {role === "business" && task.hasUnpublishedChanges && <div className="ha-task-info">Здесь показана текущая версия. В каталоге остаётся последний опубликованный снимок.</div>}
          {!task.confirmed && <div className="ha-task-info">Эта версия ещё не подтверждена: баллы за её поля пока не начислены.</div>}
          <RatingPanel rating={task.rating} />
          {GROUPS.map((group) => <section className="ha-task-card ha-task-detail-section" key={group.title}><h2>{group.title}</h2><dl>{group.fields.map((key) => <div key={key}><dt>{FIELD_LABELS[key]}</dt><dd className={!task.fields[key].trim() ? "ha-task-empty-value" : undefined}>{task.fields[key].trim() ? task.fields[key] : "Пока не указано"}</dd></div>)}</dl></section>)}
          </div>
        </div>
        <footer className="ha-task-details-actions">
          {error && <p className="ha-task-error" role="alert">{error}</p>}
          {role === "business" ? <><Button className="ha-task-primary" onClick={() => onEdit(task)}><Pencil size={16} />Редактировать задачу</Button><Button variant="outline" onClick={() => onViewProposals(task.id)}><FileCheck2 size={16} />Отклики команд</Button></> : <><div className="alem-task-student-actions">{!proposalOpen && <Button className="ha-task-primary" onClick={() => { setProposalStarted(true); setProposalOpen(true); }} disabled={saving || !task.published}><Send size={16} />{proposalStarted ? "Вернуться к отклику" : "Предложить решение"}</Button>}<Button variant="outline" className={isSaved ? "ha-task-saved-button" : undefined} onClick={() => void saveTask()} disabled={isSaved || saving || proposalBusy || !task.published}>{saving ? <Loader2 size={16} className="ha-task-spin" /> : isSaved ? <Check size={16} /> : <Bookmark size={16} />}{saving ? "Сохраняем…" : isSaved ? "В сохранённых" : "Сохранить задачу"}</Button><Button variant="ghost" disabled={saving || proposalBusy} onClick={() => onViewProposals(task.id)}><FileCheck2 size={16} />Мои отклики</Button></div><p className="ha-task-footnote">Можно откликнуться при любом рейтинге. Сохранение задачи не отправляет предложение команде бизнеса.</p></>}
        </footer>
      </>}
    </SheetContent>
  </Sheet>;
}
