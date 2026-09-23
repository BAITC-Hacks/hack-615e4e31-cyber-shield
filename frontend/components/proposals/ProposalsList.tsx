"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Inbox, Loader2, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import type { Proposal, ProposalStatus, Role } from "@/lib/contracts";
import ProposalCard, { PROPOSAL_STATUSES } from "./ProposalCard";

type Props = { role: Role; taskId?: string; teamId?: string; revision?: number; onOpenTask?: (id: string) => void; onDirtyChange?: (dirty: boolean) => void; onBusyChange?: (busy: boolean) => void };
export default function ProposalsList(props: Props) { return <ProposalListState key={`${props.role}:${props.taskId ?? ""}:${props.teamId ?? ""}`} {...props} />; }

function ProposalListState({ role, taskId, teamId, revision = 0, onOpenTask, onDirtyChange, onBusyChange }: Props) {
  const [retry, setRetry] = useState(0);
  const [result, setResult] = useState<{ key: string; proposals: Proposal[]; error: string } | null>(null);
  const [status, setStatus] = useState<ProposalStatus | "all">("all");
  const [dirtyCards, setDirtyCards] = useState<Record<string, boolean>>({});
  const [busyCards, setBusyCards] = useState<Record<string, boolean>>({});
  const reportedDirty = useRef<boolean | null>(null);
  const reportedBusy = useRef<boolean | null>(null);
  const key = `${revision}:${retry}`;
  const loading = result?.key !== key;
  const proposals = loading ? [] : result.proposals;
  const error = loading ? "" : result.error;
  const dirty = Object.values(dirtyCards).some(Boolean);
  const busy = Object.values(busyCards).some(Boolean);
  useEffect(() => {
    let cancelled = false;
    const operation = role === "business" && taskId ? api.taskProposals(taskId) : teamId ? api.teamProposals(teamId) : Promise.resolve([]);
    operation.then((data) => { if (!cancelled) setResult({ key, proposals: data, error: "" }); }).catch((cause) => { if (!cancelled) setResult({ key, proposals: [], error: cause instanceof Error ? cause.message : "Не удалось загрузить отклики." }); });
    return () => { cancelled = true; };
  }, [key, role, taskId, teamId]);
  useEffect(() => { if (reportedDirty.current !== dirty) { reportedDirty.current = dirty; onDirtyChange?.(dirty); } }, [dirty, onDirtyChange]);
  useEffect(() => { if (reportedBusy.current !== busy) { reportedBusy.current = busy; onBusyChange?.(busy); } }, [busy, onBusyChange]);
  const trackDirty = useCallback((id: string, value: boolean) => setDirtyCards((current) => current[id] === value ? current : { ...current, [id]: value }), []);
  const trackBusy = useCallback((id: string, value: boolean) => setBusyCards((current) => current[id] === value ? current : { ...current, [id]: value }), []);
  const changed = useCallback((proposal: Proposal) => setResult((current) => current ? { ...current, proposals: current.proposals.map((item) => item.id === proposal.id ? proposal : item) } : current), []);
  const visible = proposals.filter((proposal) => status === "all" || proposal.status === status);
  const acceptedTeams = new Set(proposals.filter((proposal) => proposal.status === "accepted").map((proposal) => proposal.teamId)).size;

  if (loading) return <p className="alem-proposal-loading" role="status"><Loader2 className="ha-task-spin" size={18} />Загружаем предложения…</p>;
  if (error) return <div className="alem-proposal-empty" role="alert"><p>{error}</p><Button type="button" variant="outline" onClick={() => setRetry((value) => value + 1)}><RotateCcw size={15} />Повторить загрузку</Button></div>;
  return <section className="alem-proposals-list" aria-label="Предложения команд">
    {role === "business" && <div className="alem-proposal-note">Сравните идеи, навыки, планы и сроки. Вы можете выбрать несколько команд, оставить предложения на рассмотрении или не выбрать ни одной. Каждое решение принимается вручную.</div>}
    <div className="alem-proposals-toolbar"><div><strong>Отклики: {proposals.length}</strong>{role === "business" && <span>Выбрано команд: {acceptedTeams}</span>}</div><Select value={status} onValueChange={(value) => setStatus(value as ProposalStatus | "all")} disabled={dirty || busy}><SelectTrigger aria-label="Статус отклика"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Все статусы</SelectItem>{Object.entries(PROPOSAL_STATUSES).map(([value, label]) => <SelectItem value={value} key={value}>{label}</SelectItem>)}</SelectContent></Select></div>
    {dirty && <p className="alem-proposal-hint">Сохраните или сбросьте комментарий перед сменой фильтра.</p>}
    {!visible.length ? <div className="alem-proposal-empty"><Inbox size={30} /><h3>{proposals.length ? "Нет откликов с этим статусом" : role === "business" ? "Предложения ещё не поступили" : "У команды пока нет откликов"}</h3><p>{role === "business" ? "Отклики появятся здесь после отправки студентами." : "Откройте задачу в каталоге и предложите своё решение от имени этой команды."}</p></div> : <div className="alem-proposals-grid">{visible.map((proposal) => <ProposalCard key={`${proposal.id}:${proposal.updatedAt}`} proposal={proposal} role={role} onChanged={changed} onOpenTask={onOpenTask} onDirtyChange={(value) => trackDirty(proposal.id, value)} onBusyChange={(value) => trackBusy(proposal.id, value)} />)}</div>}
  </section>;
}
