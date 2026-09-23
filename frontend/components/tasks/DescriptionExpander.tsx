"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ArrowDownToLine, CircleHelp, FileText, Loader2, RotateCcw, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type { AIExpandedDescription } from "@/lib/contracts";
import styles from "./description-expander.module.css";

type Props = {
  source: string;
  disabled?: boolean;
  resetWarning?: string;
  onApply: (description: string, expectedSource: string) => boolean;
  onBusyChange?: (busy: boolean) => void;
  onDirtyChange?: (dirty: boolean) => void;
};
type Suggestion = { result: AIExpandedDescription; source: string; version: number };

function validResponse(value: AIExpandedDescription, source: string) {
  return value && ["openai", "local_stub"].includes(value.mode) && value.confirmed === false
    && typeof value.description === "string" && value.description.trim().length > 0 && value.description.length <= 6000
    && Array.isArray(value.questions) && value.questions.length <= 6 && value.questions.every((question) => typeof question === "string" && question.trim().length > 0)
    && Array.isArray(value.warnings) && value.warnings.every((warning) => typeof warning === "string")
    && Array.isArray(value.sourceQuotes) && value.sourceQuotes.every((quote) => typeof quote === "string" && quote.trim().length > 0 && source.includes(quote))
    && typeof value.promptVersion === "string";
}

export default function DescriptionExpander({ source, disabled = false, resetWarning, onApply, onBusyChange, onDirtyChange }: Props) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [original, setOriginal] = useState("");
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const mounted = useRef(true);
  const requestVersion = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const callbacks = useRef({ onBusyChange, onDirtyChange });
  const reportedDirty = useRef(false);
  const dirty = open && suggestion !== null && draft !== suggestion.result.description;
  const stale = open && original !== source;
  const unchanged = draft.trim() === original.trim();

  useEffect(() => { callbacks.current = { onBusyChange, onDirtyChange }; }, [onBusyChange, onDirtyChange]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      requestVersion.current += 1;
      controller.current?.abort();
      controller.current = null;
      callbacks.current.onBusyChange?.(false);
      callbacks.current.onDirtyChange?.(false);
    };
  }, []);
  useEffect(() => { requestVersion.current += 1; }, [source]);
  useEffect(() => {
    if (reportedDirty.current !== dirty) { reportedDirty.current = dirty; onDirtyChange?.(dirty); }
  }, [dirty, onDirtyChange]);

  function cancel() {
    requestVersion.current += 1;
    controller.current?.abort();
    controller.current = null;
    setOpen(false);
    setBusy(false);
    setSuggestion(null);
    setDraft("");
    setError("");
    onBusyChange?.(false);
    reportedDirty.current = false;
    onDirtyChange?.(false);
  }

  async function generate() {
    if (disabled || controller.current || !source.trim() || source.length > 6000) return;
    const capturedSource = source;
    const version = ++requestVersion.current;
    const operation = new AbortController();
    controller.current = operation;
    setOpen(true);
    setBusy(true);
    setOriginal(capturedSource);
    setSuggestion(null);
    setDraft("");
    setError("");
    onBusyChange?.(true);
    try {
      const result = await api.expandDescription(capturedSource, operation.signal);
      if (!mounted.current || operation.signal.aborted) return;
      if (version !== requestVersion.current) { setError("Исходное описание изменилось. Ответ не применён: закройте окно и повторите запрос для нового текста."); return; }
      if (!validResponse(result, capturedSource)) throw new Error("ИИ вернул некорректный вариант. Ваш исходный текст сохранён. Попробуйте ещё раз или дополните его вручную.");
      setSuggestion({ result, source: capturedSource, version });
      setDraft(result.description);
    } catch (cause) {
      if (mounted.current && !operation.signal.aborted) setError(cause instanceof Error ? cause.message : "Не удалось получить вариант. Исходный текст сохранён — повторите запрос.");
    } finally {
      if (controller.current === operation) {
        controller.current = null;
        if (mounted.current) { setBusy(false); callbacks.current.onBusyChange?.(false); }
      }
    }
  }

  function apply() {
    if (!suggestion || disabled || controller.current || !draft.trim() || draft.length > 6000 || unchanged) return;
    if (suggestion.source !== source || suggestion.version !== requestVersion.current || !onApply(draft.trim(), suggestion.source)) {
      setError("Исходное описание изменилось. Этот вариант нельзя применить: закройте окно и повторите запрос для текущего текста.");
      return;
    }
    cancel();
  }

  return <div className={styles.wrapper}>
    <Button type="button" variant="outline" size="sm" className={styles.trigger} disabled={disabled || busy || !source.trim() || source.length > 6000} onClick={() => void generate()}><Sparkles size={14} />Расписать подробнее с ИИ</Button>
    <Dialog open={open} onOpenChange={(next) => { if (!next && !dirty) cancel(); }}>
      <DialogContent className={styles.dialog} showCloseButton={false} onEscapeKeyDown={(event) => { if (dirty) event.preventDefault(); }} onPointerDownOutside={(event) => { if (dirty) event.preventDefault(); }}>
        <DialogHeader><span className={styles.eyebrow}><Sparkles size={16} />ПОМОЩНИК ПО ФОРМУЛИРОВКЕ</span><DialogTitle>Расскажем о задаче подробнее</DialogTitle><DialogDescription>ИИ помогает яснее изложить ваши сведения. Проверьте и отредактируйте вариант перед использованием.</DialogDescription></DialogHeader>
        <div className={styles.original}><strong><FileText size={15} />Ваш исходный текст</strong><p>{original}</p></div>
        {busy && <div className={styles.loading} role="status"><Loader2 size={21} className="ha-task-spin" /><div><strong>Готовим и проверяем формулировку…</strong><p>Это может занять до минуты. Исходное описание остаётся на месте.</p></div></div>}
        {suggestion && <>
          <p className={`${styles.mode} ${suggestion.result.mode === "local_stub" ? styles.fallback : ""}`}><Sparkles size={14} />{suggestion.result.mode === "openai" ? "Вариант подготовлен внешним ИИ" : "Резервный режим: внешнее ИИ-расширение недоступно"}</p>
          {suggestion.result.mode === "local_stub" && suggestion.result.description.trim() === original.trim() && <p className={styles.info}>ИИ не переписал описание: ниже ваш исходный текст. Можно дополнить его вручную, опираясь на вопросы, или закрыть окно без изменений.</p>}
          <div className={styles.proposed}><label htmlFor={`${id}-draft`}>{suggestion.result.mode === "openai" ? "Предложенный вариант — можно редактировать" : "Описание — можно дополнить вручную"}</label><Textarea id={`${id}-draft`} value={draft} onChange={(event) => setDraft(event.target.value)} maxLength={6000} rows={7} aria-describedby={`${id}-count`} /><small id={`${id}-count`}>{draft.length} / 6000 символов. Используйте только сведения, которые можете подтвердить.</small></div>
          {!!suggestion.result.questions.length && <section className={styles.questions} aria-labelledby={`${id}-questions`}><h3 id={`${id}-questions`}><CircleHelp size={16} />Что ещё можно уточнить</h3><p>Ответьте на эти вопросы своими словами. Они не добавляются к описанию автоматически.</p><ul>{suggestion.result.questions.map((question, index) => <li key={`${index}-${question}`}>{question}</li>)}</ul></section>}
          {!!suggestion.result.sourceQuotes.length && <details className={styles.sources}><summary>Исходные сведения · {suggestion.result.sourceQuotes.length}</summary>{suggestion.result.sourceQuotes.map((quote, index) => <blockquote key={`${index}-${quote}`}>{quote}</blockquote>)}</details>}
          {!!suggestion.result.warnings.length && <ul className={styles.warnings}>{suggestion.result.warnings.map((warning, index) => <li key={`${index}-${warning}`}>{warning}</li>)}</ul>}
          {resetWarning && !unchanged && <p className={styles.info}>{resetWarning}</p>}
          <p className={styles.note}>«Использовать этот текст» заменит только это описание. Сохранение карточки, подтверждение сведений и публикация выполняются отдельно.</p>
        </>}
        {stale && <p className={styles.error} role="alert">Исходный текст уже изменён. Закройте окно и запросите новый вариант, чтобы не потерять правки.</p>}
        {error && <div className={styles.error} role="alert"><p>{error}</p>{!stale && <Button type="button" variant="outline" size="sm" disabled={busy || disabled} onClick={() => void generate()}><RotateCcw size={14} />Повторить запрос</Button>}</div>}
        <DialogFooter><Button type="button" variant="outline" onClick={cancel}>{busy ? "Отменить ожидание" : "Отмена"}</Button>{suggestion && <Button type="button" className="ha-task-primary" disabled={busy || disabled || stale || !draft.trim() || draft.length > 6000 || unchanged} onClick={apply}><ArrowDownToLine size={15} />Использовать этот текст</Button>}</DialogFooter>
      </DialogContent>
    </Dialog>
  </div>;
}
