"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { CheckCircle2, FileText, Loader2, Send, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { api } from "@/lib/api";
import type { Proposal, Task } from "@/lib/contracts";
import TeamPicker from "./TeamPicker";

type Props = { task: Task; teamId: string; onTeamChange: (id: string) => void; onSubmitted: (proposal: Proposal) => void; onDirtyChange?: (dirty: boolean) => void; onBusyChange?: (busy: boolean) => void };
const lines = (value: string) => value.split("\n").map((line) => line.trim()).filter(Boolean);

export default function ProposalForm({ task, teamId, onTeamChange, onSubmitted, onDirtyChange, onBusyChange }: Props) {
  const prefix = useId();
  const [initialTeam, setInitialTeam] = useState(teamId);
  const [pendingTeam, setPendingTeam] = useState<string | null>(null);
  const [idea, setIdea] = useState("");
  const [plan, setPlan] = useState("");
  const [duration, setDuration] = useState("");
  const [url, setUrl] = useState("");
  const [assumptions, setAssumptions] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState<Proposal | null>(null);
  const mounted = useRef(true);
  const locked = useRef(false);
  const reportedDirty = useRef<boolean | null>(null);
  const dirty = !sent && (teamId !== initialTeam || !!file || [idea, plan, duration, url, assumptions].some((value) => !!value.trim()));
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (reportedDirty.current !== dirty) { reportedDirty.current = dirty; onDirtyChange?.(dirty); }
  }, [dirty, onDirtyChange]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (locked.current || sent) return;
    const steps = lines(plan);
    const assumptionsList = lines(assumptions);
    if (!task.published) { setError("Отклик можно отправить после публикации задачи."); return; }
    if (!teamId) { setError("Выберите тестовую команду, от имени которой отправляете отклик."); return; }
    if (!idea.trim()) { setError("Опишите идею решения."); return; }
    if (!steps.length || steps.length > 20 || steps.some((step) => step.length > 1000)) { setError("В плане должно быть от 1 до 20 шагов, каждый не длиннее 1000 символов."); return; }
    const days = Number(duration);
    if (!Number.isInteger(days) || days < 1 || days > 365) { setError("Укажите срок целым числом от 1 до 365 дней."); return; }
    let validUrl = false;
    try { const raw = url.trim(); const parsed = new URL(raw); validUrl = /^https?:\/\//i.test(raw) && ["http:", "https:"].includes(parsed.protocol) && !/[\s\u0000-\u001f]/.test(raw); } catch { /* Display a useful inline validation message below. */ }
    if (!validUrl) { setError("Укажите полную ссылку на прототип, начинающуюся с https:// или http://, без пробелов."); return; }
    if (assumptionsList.length > 20 || assumptionsList.some((item) => item.length > 1000)) { setError("Укажите не более 20 допущений, каждое не длиннее 1000 символов."); return; }
    locked.current = true;
    setBusy(true);
    onBusyChange?.(true);
    setError("");
    try {
      const input = { teamId, idea: idea.trim(), plan: steps, durationDays: days, prototypeUrl: url.trim(), assumptions: assumptionsList };
      const result = file ? await api.uploadProposal(task.id, input, file) : await api.submitProposal(task.id, input);
      if (!mounted.current) return;
      setSent(result);
      reportedDirty.current = false;
      onDirtyChange?.(false);
      onSubmitted(result);
    } catch (cause) {
      if (mounted.current) setError(cause instanceof Error ? cause.message : "Не удалось отправить отклик. Ваш текст сохранён в этой форме — повторите попытку.");
    } finally {
      locked.current = false;
      if (mounted.current) { setBusy(false); onBusyChange?.(false); }
    }
  }

  if (sent) return <section className="alem-proposal-success" role="status"><CheckCircle2 size={30} /><h3>Предложение отправлено</h3><p>Команда <strong>{sent.team.name}</strong> откликнулась на задачу. Статус — «На рассмотрении».</p>{!!sent.attachments?.length && <p>PDF приложен к отклику и доступен бизнесу для скачивания.</p>}<p>Бизнес сравнит предложения и примет решение. Статус доступен в разделе «Мои отклики».</p><Button type="button" variant="outline" onClick={() => { setInitialTeam(teamId); setSent(null); setIdea(""); setPlan(""); setDuration(""); setUrl(""); setAssumptions(""); setFile(null); setError(""); }}>Подготовить ещё один отклик</Button></section>;
  return <form onSubmit={submit} className="alem-proposal-form" noValidate>
    <div className="alem-proposal-intro"><h3>Предложите своё решение</h3><p>Отклик доступен на любую опубликованную задачу. Сохранение квеста и предложение команды — разные действия.</p></div>
    <TeamPicker value={teamId} onChange={(id) => { if (id === teamId) return; if (teamId && dirty) setPendingTeam(id); else onTeamChange(id); }} disabled={busy} />
    <div className="alem-proposal-field"><label htmlFor={`${prefix}-idea`}>Идея решения <span>обязательно</span></label><Textarea id={`${prefix}-idea`} value={idea} onChange={(event) => setIdea(event.target.value)} placeholder="Как вы предлагаете решить задачу и чем это поможет бизнесу?" rows={4} maxLength={6000} disabled={busy} required /></div>
    <div className="alem-proposal-field"><label htmlFor={`${prefix}-plan`}>План работы <span>обязательно</span></label><Textarea id={`${prefix}-plan`} value={plan} onChange={(event) => setPlan(event.target.value)} placeholder={"Изучить процесс и данные\nСобрать прототип\nПроверить результат с бизнесом"} rows={4} maxLength={20020} disabled={busy} required /><small>Каждый шаг с новой строки. От 1 до 20 шагов.</small></div>
    <div className="alem-proposal-field"><label htmlFor={`${prefix}-duration`}>Срок в днях <span>обязательно</span></label><Input id={`${prefix}-duration`} type="number" min={1} max={365} step={1} inputMode="numeric" value={duration} onChange={(event) => setDuration(event.target.value)} placeholder="Например, 14" disabled={busy} required /></div>
    <div className="alem-proposal-field"><label htmlFor={`${prefix}-url`}>Ссылка на прототип <span>обязательно</span></label><Input id={`${prefix}-url`} type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://…" maxLength={2048} disabled={busy} required /><small>Полная ссылка HTTP(S) на прототип или демонстрацию решения.</small></div>
    <div className="alem-proposal-field"><label htmlFor={`${prefix}-assumptions`}>Допущения и вопросы <span>необязательно</span></label><Textarea id={`${prefix}-assumptions`} value={assumptions} onChange={(event) => setAssumptions(event.target.value)} placeholder="Какие доступы или уточнения понадобятся? Каждое допущение с новой строки." maxLength={20020} rows={3} disabled={busy} /></div>
    <div className="alem-proposal-field"><label htmlFor={`${prefix}-pdf`}>Презентация или описание в PDF <span>необязательно</span></label><Input ref={fileInput} id={`${prefix}-pdf`} type="file" accept="application/pdf,.pdf" disabled={busy} onChange={(event) => {
      const selected = event.target.files?.[0];
      if (!selected) return;
      if (!selected.name.toLowerCase().endsWith(".pdf") || (selected.type && selected.type !== "application/pdf")) { setFile(null); setError("Можно приложить только PDF-файл."); event.target.value = ""; return; }
      if (selected.size > 10 * 1024 * 1024 || selected.size === 0) { setFile(null); setError("PDF должен быть непустым и не больше 10 МиБ."); event.target.value = ""; return; }
      setFile(selected); setError("");
    }} /><small>Один PDF до 10 МиБ. Файл дополняет описание и ссылку на прототип.</small>{file && <div className="alem-proposal-attachment"><FileText size={18} /><span><strong>{file.name}</strong><small>{(file.size / 1024).toLocaleString("ru", { maximumFractionDigits: 1 })} КБ · будет отправлен вместе с откликом</small></span><Button type="button" size="icon" variant="ghost" disabled={busy} aria-label="Убрать PDF" onClick={() => { setFile(null); if (fileInput.current) fileInput.current.value = ""; }}><X size={16} /></Button></div>}</div>
    {error && <p role="alert" className="alem-proposal-error">{error}</p>}
    <Button type="submit" className="ha-task-primary" disabled={busy || !task.published}>{busy ? <Loader2 size={16} className="ha-task-spin" /> : <Send size={16} />}{busy ? "Отправляем предложение…" : "Отправить предложение"}</Button>
    <p className="alem-proposal-hint">Количество откликов не ограничено. Отправка предложения не назначает вашу команду исполнителем.</p>
    <AlertDialog open={!!pendingTeam} onOpenChange={(open) => { if (!open) setPendingTeam(null); }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Отправить от другой команды?</AlertDialogTitle><AlertDialogDescription>Текст предложения сохранится в форме, но при отправке будет принадлежать новой выбранной команде.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>Оставить команду</AlertDialogCancel><AlertDialogAction onClick={() => { if (pendingTeam) onTeamChange(pendingTeam); setPendingTeam(null); }}>Сменить команду</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </form>;
}
