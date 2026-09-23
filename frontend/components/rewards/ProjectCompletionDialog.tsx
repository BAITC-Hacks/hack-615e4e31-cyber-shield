"use client";

import { useEffect, useId, useRef, useState } from "react";
import { CheckCheck, Loader2, Trophy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type { Proposal } from "@/lib/contracts";
import styles from "./completion.module.css";

type Props = { proposal: Proposal; disabled: boolean; onChanged: (proposal: Proposal) => void; onDirtyChange: (dirty: boolean) => void; onBusyChange: (busy: boolean) => void };

export default function ProjectCompletionDialog({ proposal, disabled, onChanged, onDirtyChange, onBusyChange }: Props) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [summary, setSummary] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false);
  const mounted = useRef(true);
  const reportedDirty = useRef<boolean | null>(null);
  const dirty = summary.length > 0 || confirmed;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { if (reportedDirty.current !== dirty) { reportedDirty.current = dirty; onDirtyChange(dirty); } }, [dirty, onDirtyChange]);
  function cancel() { if (lock.current) return; setOpen(false); setSummary(""); setConfirmed(false); setError(""); }
  async function complete() {
    if (lock.current || !confirmed || summary.trim().length < 10) return;
    lock.current = true;
    setBusy(true);
    setError("");
    onBusyChange(true);
    try {
      const updated = await api.completeProposal(proposal.id, summary.trim());
      if (mounted.current) {
        setOpen(false);
        setSummary("");
        setConfirmed(false);
        reportedDirty.current = false;
        onDirtyChange(false);
        onBusyChange(false);
        onChanged(updated);
      }
    } catch (cause) { if (mounted.current) setError(cause instanceof Error ? cause.message : "Не удалось подтвердить завершение. Повторите попытку."); }
    finally { lock.current = false; if (mounted.current) { setBusy(false); onBusyChange(false); } }
  }
  return <Dialog open={open} onOpenChange={(next) => { if (!busy && (!dirty || next)) setOpen(next); }}>
    <Button type="button" variant="outline" className={styles.trigger} disabled={disabled || busy} onClick={() => setOpen(true)}><CheckCheck size={16} />Подтвердить завершение</Button>
    <DialogContent showCloseButton={false} className={styles.dialog} onEscapeKeyDown={(event) => { if (busy || dirty) event.preventDefault(); }} onPointerDownOutside={(event) => { if (busy || dirty) event.preventDefault(); }}>
      <DialogHeader><div className={styles.icon}><Trophy size={25} /></div><DialogTitle>Проект успешно завершён?</DialogTitle><DialogDescription>Подтвердите результат работы команды «{proposal.team.name}» по задаче «{proposal.taskTitle}».</DialogDescription></DialogHeader>
      <div className={styles.award}><strong>+100 баллов команде</strong><p>После вашего подтверждения баллы можно обменять на фон профиля и предметы для виртуальной комнаты. Награда выдаётся один раз за эту задачу и команду.</p></div>
      <div className={styles.field}><label htmlFor={`${id}-summary`}>Что команда сделала и что вы проверили</label><Textarea id={`${id}-summary`} rows={4} value={summary} onChange={(event) => setSummary(event.target.value)} disabled={busy} minLength={10} maxLength={2000} placeholder="Например: проверили готовый прототип на тестовых данных, согласованные критерии выполнены." aria-describedby={`${id}-summary-help`} /><small id={`${id}-summary-help`}>От 10 до 2000 символов. Результат будет виден команде.</small></div>
      <label className={styles.confirm} htmlFor={`${id}-confirmed`}><Checkbox id={`${id}-confirmed`} checked={confirmed} onCheckedChange={(value) => setConfirmed(value === true)} disabled={busy} /><span>Я проверил результат и подтверждаю успешное завершение проекта.</span></label>
      <p className={styles.hint}>После подтверждения выбор команды и результат завершения фиксируются.</p>
      {error && <p className={styles.error} role="alert">{error}</p>}
      <DialogFooter><Button type="button" variant="outline" disabled={busy} onClick={cancel}>Отменить подтверждение</Button><Button type="button" className="ha-task-primary" disabled={busy || !confirmed || summary.trim().length < 10} onClick={() => void complete()}>{busy ? <Loader2 size={15} className="ha-task-spin" /> : <CheckCheck size={15} />}Подтвердить результат</Button></DialogFooter>
    </DialogContent>
  </Dialog>;
}
