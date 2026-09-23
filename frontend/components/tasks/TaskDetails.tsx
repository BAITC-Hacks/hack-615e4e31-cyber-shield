"use client";

import { useEffect, useRef, useState } from "react";
import { Bookmark, Check, Loader2, Pencil, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { Role, Task, TaskFields } from "@/lib/contracts";
import RatingPanel, { FIELD_LABELS } from "./RatingPanel";

type Props = {
  task: Task | null; role: Role; saved: boolean; onClose: () => void;
  onEdit: (task: Task) => void; onSave: (task: Task) => Promise<void>;
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

function TaskDetailsSheet({ task, role, saved, onClose, onEdit, onSave }: Props) {
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
    setError(null);
    try {
      await onSave(selectedTask);
      if (mounted.current) setSavedId(selectedTask.id);
    } catch (cause) {
      if (mounted.current) setError(cause instanceof Error ? cause.message : "Не удалось сохранить задачу. Попробуйте ещё раз.");
    } finally {
      savingLock.current = false;
      if (mounted.current) setSaving(false);
    }
  }

  const isSaved = saved || (!!task && savedId === task.id);
  return <Sheet open={!!task} onOpenChange={(open) => { if (!open) onClose(); }}>
    <SheetContent className="ha-task-details" showCloseButton={false}>
      {task && <>
        <Button variant="ghost" size="icon" onClick={onClose} className="ha-task-details-close" aria-label="Закрыть карточку"><X size={20} /></Button>
        <SheetHeader className="ha-task-details-header">
          <div className="ha-task-eyebrow">{task.topic || "Без направления"}</div>
          <SheetTitle>{task.fields.title || "Задача без названия"}</SheetTitle>
          <SheetDescription>{task.company || "Компания не указана"} · {task.published ? "Опубликована" : "Черновик"}</SheetDescription>
          {!!task.requiredSkills.length && <div className="ha-task-skills">{task.requiredSkills.map((skill) => <span className="ha-task-skill-label" key={skill}>{skill}</span>)}</div>}
        </SheetHeader>
        <div className="ha-task-details-body">
          {role === "business" && task.hasUnpublishedChanges && <div className="ha-task-info">Здесь показана текущая версия. В каталоге остаётся последний опубликованный снимок.</div>}
          {!task.confirmed && <div className="ha-task-info">Эта версия ещё не подтверждена: баллы за её поля пока не начислены.</div>}
          <RatingPanel rating={task.rating} />
          {GROUPS.map((group) => <section className="ha-task-card ha-task-detail-section" key={group.title}><h2>{group.title}</h2><dl>{group.fields.map((key) => <div key={key}><dt>{FIELD_LABELS[key]}</dt><dd className={!task.fields[key].trim() ? "ha-task-empty-value" : undefined}>{task.fields[key].trim() ? task.fields[key] : "Пока не указано"}</dd></div>)}</dl></section>)}
        </div>
        <footer className="ha-task-details-actions">
          {error && <p className="ha-task-error" role="alert">{error}</p>}
          {role === "business" ? <Button className="ha-task-primary" onClick={() => onEdit(task)}><Pencil size={16} /> Редактировать задачу</Button> : <><Button className={isSaved ? "ha-task-saved-button" : "ha-task-primary"} onClick={() => void saveTask()} disabled={isSaved || saving || !task.published}>{saving ? <Loader2 size={16} className="ha-task-spin" /> : isSaved ? <Check size={16} /> : <Bookmark size={16} />}{saving ? "Сохраняем…" : isSaved ? "В сохранённых" : "Сохранить задачу"}</Button><p className="ha-task-footnote">Сохранение отмечает ваш интерес и не назначает команду исполнителем.</p></>}
        </footer>
      </>}
    </SheetContent>
  </Sheet>;
}
