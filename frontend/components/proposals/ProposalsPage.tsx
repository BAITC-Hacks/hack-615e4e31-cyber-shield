"use client";

import { useId } from "react";
import { FileCheck2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { Role, Task } from "@/lib/contracts";
import ProposalsList from "./ProposalsList";
import TeamPicker from "./TeamPicker";

type Props = {
  role: Role; tasks: Task[]; loading: boolean; error: string; onRetry: () => void;
  taskId: string; onTaskChange: (id: string) => void; teamId: string; onTeamChange: (id: string) => void;
  dirty: boolean; busy: boolean; onDirtyChange: (dirty: boolean) => void; onBusyChange: (busy: boolean) => void;
  onOpenTask: (id: string) => void; onCatalog: () => void;
  revision: number;
};
export default function ProposalsPage({ role, tasks, loading, error, onRetry, taskId, onTaskChange, teamId, onTeamChange, dirty, busy, onDirtyChange, onBusyChange, onOpenTask, onCatalog, revision }: Props) {
  const id = useId();
  const selectedTask = tasks.find((task) => task.id === taskId);
  return <div className="alem-proposals-page"><div className="page-heading"><div><div className="eyebrow">{role === "business" ? "ВЫБОР БИЗНЕСА" : "ПРЕДЛОЖЕНИЯ КОМАНДЫ"}</div><h1>{role === "business" ? <>Отклики <em className="hero-emphasis">команд</em></> : <>Мои <em className="hero-emphasis">отклики</em></>}<span className="heading-dot">.</span></h1><p>{role === "business" ? "Сравнивайте предложения и выбирайте, с кем продолжить работу." : "Предложения вашей тестовой команды и решения бизнеса."}</p></div><Button variant="outline" onClick={onCatalog}>К каталогу задач</Button></div>
    {role === "student" ? <TeamPicker value={teamId} onChange={onTeamChange} disabled={dirty || busy} /> : <section className="alem-proposal-task-picker"><label htmlFor={id}>Задача для сравнения откликов</label>{loading ? <p className="alem-proposal-loading" role="status"><Loader2 className="ha-task-spin" size={16} />Загружаем задачи…</p> : error ? <div className="alem-proposal-error" role="alert"><p>{error}</p><Button variant="outline" onClick={onRetry}>Повторить</Button></div> : <Select value={selectedTask ? taskId : ""} onValueChange={onTaskChange} disabled={dirty || busy || !tasks.length}><SelectTrigger id={id}><SelectValue placeholder="Выберите задачу" /></SelectTrigger><SelectContent>{tasks.map((task) => <SelectItem value={task.id} key={task.id}>{task.fields.title || "Без названия"}{!task.published ? " · черновик" : ""}</SelectItem>)}</SelectContent></Select>}{dirty && <p className="alem-proposal-hint">Сохраните или сбросьте комментарий перед выбором другой задачи.</p>}</section>}
    {((role === "student" && teamId) || (role === "business" && selectedTask)) ? <ProposalsList revision={revision} role={role} teamId={role === "student" ? teamId : undefined} taskId={role === "business" ? taskId : undefined} onOpenTask={onOpenTask} onDirtyChange={onDirtyChange} onBusyChange={onBusyChange} /> : !loading || role === "student" ? <div className="alem-proposal-empty"><FileCheck2 size={32} /><h3>{role === "business" ? "Выберите задачу" : "Выберите свою команду"}</h3><p>{role === "business" ? "Здесь можно сравнить все поступившие предложения по выбранной задаче." : "Команда для откликов выбирается отдельно от личного профиля для рекомендаций."}</p></div> : null}
  </div>;
}
