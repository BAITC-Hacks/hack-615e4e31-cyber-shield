"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ArrowUpRight, Check, Clock3, Download, ExternalLink, FileText, Loader2, RotateCcw, Save, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type { Proposal, ProposalAttachment, ProposalStatus, Role } from "@/lib/contracts";

export const PROPOSAL_STATUSES: Record<ProposalStatus, string> = { submitted: "На рассмотрении", accepted: "Команда выбрана", rejected: "Отклонён" };
type Props = { proposal: Proposal; role: Role; onChanged: (proposal: Proposal) => void; onOpenTask?: (taskId: string) => void; onDirtyChange: (dirty: boolean) => void; onBusyChange: (busy: boolean) => void };

function formatDate(value: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Дата не указана" : new Intl.DateTimeFormat("ru", { day: "numeric", month: "short", year: "numeric" }).format(parsed);
}

export default function ProposalCard({ proposal, role, onChanged, onOpenTask, onDirtyChange, onBusyChange }: Props) {
  const commentId = useId();
  const [comment, setComment] = useState(proposal.decisionComment);
  const [busy, setBusy] = useState<ProposalStatus | null>(null);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState("");
  const lock = useRef(false);
  const mounted = useRef(true);
  const reportedDirty = useRef<boolean | null>(null);
  const dirty = role === "business" && comment !== proposal.decisionComment;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { if (reportedDirty.current !== dirty) { reportedDirty.current = dirty; onDirtyChange(dirty); } }, [dirty, onDirtyChange]);
  let safeUrl = false;
  try { safeUrl = /^https?:\/\//i.test(proposal.prototypeUrl) && !/[\s\u0000-\u001f]/.test(proposal.prototypeUrl) && ["http:", "https:"].includes(new URL(proposal.prototypeUrl).protocol); } catch { /* Invalid links are shown as text only. */ }

  async function decide(status: ProposalStatus) {
    if (lock.current) return;
    lock.current = true;
    setBusy(status);
    onBusyChange(true);
    setError("");
    try {
      const updated = await api.decideProposal(proposal.id, status, comment);
      if (mounted.current) {
        reportedDirty.current = false;
        onDirtyChange(false);
        onBusyChange(false);
        onChanged(updated);
      }
    } catch (cause) { if (mounted.current) setError(cause instanceof Error ? cause.message : "Не удалось сохранить решение. Повторите попытку."); }
    finally { lock.current = false; if (mounted.current) { setBusy(null); onBusyChange(false); } }
  }

  async function download(attachment: ProposalAttachment) {
    if (downloading) return;
    setDownloading(attachment.id);
    setDownloadError("");
    try {
      const blob = await api.downloadProposalAttachment(proposal.id, attachment.id, role, proposal.teamId);
      if (!mounted.current) return;
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = attachment.name;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (cause) { if (mounted.current) setDownloadError(cause instanceof Error ? cause.message : "Не удалось скачать PDF."); }
    finally { if (mounted.current) setDownloading(null); }
  }

  return <article className={`alem-proposal-card alem-proposal-${proposal.status}`}>
    <header className="alem-proposal-card-header"><div><span className="alem-proposal-kicker">Предложение команды</span><h3>{proposal.team.name}</h3><small>{formatDate(proposal.createdAt)}</small></div><span className={`alem-proposal-status alem-proposal-status-${proposal.status}`}>{PROPOSAL_STATUSES[proposal.status]}</span></header>
    {onOpenTask && <Button type="button" variant="ghost" className="alem-proposal-task-link" onClick={() => onOpenTask(proposal.taskId)}>{proposal.taskTitle || "Открыть задачу"}<ArrowUpRight size={15} /></Button>}
    <div className="alem-proposal-team-facts"><div className="alem-proposal-tags">{proposal.team.skills.length ? proposal.team.skills.map((skill) => <span key={skill}>{skill}</span>) : <span>Навыки не указаны</span>}</div><p><strong>Технологии:</strong> {proposal.team.technologies.join(", ") || "Не указаны"}</p><p><strong>Интересы:</strong> {proposal.team.interests.join(", ") || "Не указаны"}</p></div>
    <dl className="alem-proposal-content"><div><dt>Идея решения</dt><dd>{proposal.idea}</dd></div><div><dt>План работы</dt><dd><ol>{proposal.plan.map((step, index) => <li key={`${index}-${step}`}>{step}</li>)}</ol></dd></div><div><dt><Clock3 size={14} />Предложенный срок</dt><dd>{proposal.durationDays} дн.</dd></div><div><dt>Прототип</dt><dd>{proposal.prototypeIsPlaceholder ? <div className="alem-proposal-placeholder"><span>{proposal.prototypeUrl}</span><small>Ссылка на демонстрационный домен. Рабочий прототип по ней не подтверждён.</small></div> : safeUrl ? <a className="alem-proposal-url" href={proposal.prototypeUrl} target="_blank" rel="noopener noreferrer">{proposal.prototypeUrl}<ExternalLink size={13} /></a> : <span>{proposal.prototypeUrl || "Не указан"}</span>}</dd></div><div><dt>Допущения</dt><dd>{proposal.assumptions.length ? <ul>{proposal.assumptions.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul> : <span className="alem-proposal-muted">Не указаны</span>}</dd></div></dl>
    {!!proposal.attachments?.length && <section className="alem-proposal-attachments" aria-label="Прикреплённые PDF"><h4>Материалы команды</h4>{proposal.attachments.map((attachment) => <div className="alem-proposal-attachment" key={attachment.id}><FileText size={18} /><span><strong>{attachment.name}</strong><small>PDF · {(attachment.size / 1024).toLocaleString("ru", { maximumFractionDigits: 1 })} КБ</small></span><Button type="button" variant="outline" size="sm" disabled={!!downloading} onClick={() => void download(attachment)} aria-label={`Скачать ${attachment.name}`}>{downloading === attachment.id ? <Loader2 className="ha-task-spin" size={15} /> : <Download size={15} />}Скачать</Button></div>)}{downloadError && <p role="alert" className="alem-proposal-error">{downloadError}</p>}</section>}
    {role === "business" ? <div className="alem-proposal-decision"><div className="alem-proposal-field"><label htmlFor={commentId}>Комментарий команде <span>необязательно</span></label><Textarea id={commentId} value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Обратная связь или следующие шаги" maxLength={2000} rows={3} disabled={!!busy} /></div>{error && <p className="alem-proposal-error" role="alert">{error}</p>}<div className="alem-proposal-decision-buttons">{proposal.status !== "accepted" && <Button type="button" className="ha-task-primary" disabled={!!busy} onClick={() => void decide("accepted")}>{busy === "accepted" ? <Loader2 size={15} className="ha-task-spin" /> : <Check size={15} />}Выбрать команду</Button>}{proposal.status !== "rejected" && <Button type="button" variant="outline" disabled={!!busy} onClick={() => void decide("rejected")}>{busy === "rejected" ? <Loader2 size={15} className="ha-task-spin" /> : <X size={15} />}Отклонить</Button>}{proposal.status !== "submitted" && <Button type="button" variant="outline" disabled={!!busy} onClick={() => void decide("submitted")}>{busy === "submitted" ? <Loader2 size={15} className="ha-task-spin" /> : <RotateCcw size={15} />}На рассмотрение</Button>}{dirty && <><Button type="button" variant="outline" disabled={!!busy} onClick={() => void decide(proposal.status)}><Save size={15} />Сохранить комментарий</Button><Button type="button" variant="ghost" disabled={!!busy} onClick={() => setComment(proposal.decisionComment)}>Сбросить комментарий</Button></>}</div></div> : proposal.decisionComment ? <div className="alem-proposal-feedback"><strong>Комментарий бизнеса</strong><p>{proposal.decisionComment}</p></div> : <p className="alem-proposal-hint">{proposal.status === "submitted" ? "Предложение ожидает решения бизнеса." : proposal.status === "accepted" ? "Бизнес выбрал вашу команду. Следующие шаги можно уточнить по контакту в задаче." : "Бизнес отклонил это предложение. Можно подготовить новый отклик."}</p>}
  </article>;
}
