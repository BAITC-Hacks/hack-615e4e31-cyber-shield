"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDownToLine, Check, ChevronDown, FileText, Loader2, MessageSquare, RotateCcw, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { api } from "@/lib/api";
import { EMPTY_FIELDS, type AIAnalysis, type AIAnswer, type AICardResult, type AIMode, type TaskFields } from "@/lib/contracts";
import { FIELD_LABELS } from "./RatingPanel";

type Props = {
  fields: TaskFields;
  formSnapshot: string;
  disabled: boolean;
  onApply: (fields: TaskFields, expectedSnapshot: string) => boolean;
  onDirtyChange?: (dirty: boolean) => void;
};
type AnalysisState = { result: AIAnalysis; inputKey: string };
type ProposalState = { result: AICardResult; inputKey: string; formSnapshot: string; answers: AIAnswer[] };
const FIELD_KEYS = Object.keys(EMPTY_FIELDS) as (keyof TaskFields)[];
const INVALID_RESPONSE = "Помощник вернул некорректный ответ. Повторите запрос или заполните карточку вручную.";

function isMode(value: unknown): value is AIMode { return value === "local_stub" || value === "openai"; }
function isField(value: unknown): value is keyof TaskFields { return typeof value === "string" && FIELD_KEYS.includes(value as keyof TaskFields); }
function validAnalysis(value: AIAnalysis) {
  return value && isMode(value.mode) && Array.isArray(value.questions) && (value.questions.length === 0 || (value.questions.length >= 3 && value.questions.length <= 6))
    && new Set(value.questions.map((question) => question?.id)).size === value.questions.length
    && value.questions.every((question) => question && isField(question.field) && typeof question.id === "string" && typeof question.question === "string" && question.question.trim())
    && Array.isArray(value.warnings) && value.warnings.every((warning) => typeof warning === "string")
    && Array.isArray(value.missingFields) && value.missingFields.every(isField);
}
function validCard(value: AICardResult) {
  return value && isMode(value.mode) && value.confirmed === false && value.fields && value.sources
    && FIELD_KEYS.every((key) => typeof value.fields[key] === "string" && Array.isArray(value.sources[key])
      && value.sources[key].every((source) => source && typeof source.sourceId === "string" && typeof source.quote === "string"))
    && Array.isArray(value.warnings) && value.warnings.every((warning) => typeof warning === "string");
}

export default function AIAssistant({ fields, formSnapshot, disabled, onApply, onDirtyChange }: Props) {
  const [open, setOpen] = useState(false);
  const [description, setDescription] = useState("");
  const [analysis, setAnalysis] = useState<AnalysisState | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [proposal, setProposal] = useState<ProposalState | null>(null);
  const [busy, setBusy] = useState<"analyze" | "build" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [failedAction, setFailedAction] = useState<"analyze" | "build" | null>(null);
  const [applied, setApplied] = useState(false);
  const mounted = useRef(true);
  const requestVersion = useRef(0);
  const busyLock = useRef(false);
  const reportedDirty = useRef<boolean | null>(null);
  const dirty = !applied && (!!description.trim() || Object.values(answers).some((answer) => !!answer.trim()));
  const inputKey = JSON.stringify({ description, formSnapshot });
  const analysisCurrent = analysis?.inputKey === inputKey;
  const proposalCurrent = proposal?.inputKey === inputKey;
  const stale = !applied && ((analysis !== null && !analysisCurrent) || (proposal !== null && !proposalCurrent));
  const mode = proposal?.result.mode ?? analysis?.result.mode;
  const warnings = proposalCurrent ? proposal?.result.warnings : analysisCurrent ? analysis?.result.warnings : [];

  useEffect(() => {
    if (reportedDirty.current !== dirty) {
      reportedDirty.current = dirty;
      onDirtyChange?.(dirty);
    }
  }, [dirty, onDirtyChange]);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; requestVersion.current += 1; };
  }, []);
  useEffect(() => { requestVersion.current += 1; }, [formSnapshot]);

  function changeDescription(value: string) {
    requestVersion.current += 1;
    setDescription(value);
    setAnalysis(null);
    setAnswers({});
    setProposal(null);
    setError(null);
    setFailedAction(null);
    setApplied(false);
  }
  function changeAnswer(id: string, value: string) {
    requestVersion.current += 1;
    setAnswers((current) => ({ ...current, [id]: value }));
    setProposal(null);
    setError(null);
    setFailedAction(null);
    setApplied(false);
  }

  async function run(action: "analyze" | "build") {
    if (disabled || busyLock.current) return;
    if (!description.trim()) { setError("Сначала коротко опишите свою задачу."); return; }
    if (action === "build" && !analysisCurrent) { setError("Карточка изменилась. Сначала обновите уточняющие вопросы."); return; }
    const version = ++requestVersion.current;
    const capturedKey = inputKey;
    const capturedSnapshot = formSnapshot;
    const currentAnswers = (analysis?.result.questions ?? []).map((question) => ({ field: question.field, answer: answers[question.id] ?? "" }));
    busyLock.current = true;
    setBusy(action);
    setError(null);
    setFailedAction(null);
    setApplied(false);
    try {
      const result = action === "analyze"
        ? await api.analyzeTask(description, fields)
        : await api.buildTaskCard(description, fields, currentAnswers);
      if (!mounted.current) return;
      if (requestVersion.current !== version) {
        setError("Во время запроса карточка изменилась. Ответ не применён — повторите анализ для текущей версии.");
        setFailedAction("analyze");
        return;
      }
      if (action === "analyze") {
        if (!validAnalysis(result as AIAnalysis)) throw new Error(INVALID_RESPONSE);
        setAnalysis({ result: result as AIAnalysis, inputKey: capturedKey });
        setAnswers({});
        setProposal(null);
      } else {
        if (!validCard(result as AICardResult)) throw new Error(INVALID_RESPONSE);
        setProposal({ result: result as AICardResult, inputKey: capturedKey, formSnapshot: capturedSnapshot, answers: currentAnswers });
      }
    } catch (cause) {
      if (mounted.current) {
        setError(cause instanceof Error ? cause.message : "Не удалось получить ответ помощника. Попробуйте ещё раз.");
        setFailedAction(action);
      }
    } finally {
      busyLock.current = false;
      if (mounted.current) setBusy(null);
    }
  }

  function applyProposal() {
    if (!proposal || !proposalCurrent || disabled || busyLock.current) return;
    if (!onApply(proposal.result.fields, proposal.formSnapshot)) {
      setError("Карточка изменилась. Соберите новый вариант, чтобы сохранить свои правки.");
      setFailedAction("analyze");
      return;
    }
    setApplied(true);
    setError(null);
    setFailedAction(null);
  }

  function sourceLabel(sourceId: string) {
    if (sourceId === "description") return "Исходное описание";
    if (sourceId.startsWith("fields.")) return `Текущая карточка · ${FIELD_LABELS[sourceId.slice(7)] ?? "поле"}`;
    if (sourceId.startsWith("answers.")) {
      const answer = proposal?.answers[Number(sourceId.slice(8))];
      return answer ? `Ваш ответ · ${FIELD_LABELS[answer.field]}` : "Ваш ответ";
    }
    return "Предоставленные сведения";
  }

  return <Collapsible open={open} onOpenChange={setOpen} className="ha-task-card ha-task-ai">
    <CollapsibleTrigger asChild><Button type="button" variant="ghost" className="ha-task-ai-trigger">
      <span className="ha-task-ai-symbol"><Sparkles size={19} /></span>
      <span><strong>Помощник по описанию задачи</strong><small>Уточняющие вопросы и черновик из ваших ответов</small></span>
      <ChevronDown size={18} className={open ? "ha-task-ai-chevron-open" : ""} />
    </Button></CollapsibleTrigger>
    <CollapsibleContent className="ha-task-ai-content">
      <p className="ha-task-ai-intro">Расскажите о задаче своими словами. Помощник уточнит недостающие сведения и предложит карточку. Вы проверите её перед переносом.</p>
      <div className="ha-task-field"><label htmlFor="ai-task-description">Исходное описание</label><Textarea id="ai-task-description" value={description} onChange={(event) => changeDescription(event.target.value)} maxLength={6000} rows={3} disabled={disabled || !!busy} placeholder="Например, хотим сократить время ответа на вопросы клиентов. Сейчас менеджеры отвечают вручную." /></div>
      <div className="ha-task-ai-actions"><Button type="button" variant="outline" onClick={() => void run("analyze")} disabled={disabled || !!busy || !description.trim()}>{busy === "analyze" ? <Loader2 size={16} className="ha-task-spin" /> : <MessageSquare size={16} />}{analysis ? "Обновить вопросы" : "Уточнить задачу"}</Button><span className="ha-task-field-hint">Текущие поля карточки тоже будут учтены.</span></div>
      {busy && <p className="ha-task-inline-status" role="status">{busy === "analyze" ? "Изучаем описание и готовим вопросы…" : "Собираем предварительную карточку…"}</p>}
      {mode && <div className={`ha-task-ai-mode ${mode === "local_stub" ? "ha-task-ai-mode-stub" : ""}`}><Sparkles size={14} />{mode === "local_stub" ? "Резервный режим без внешней AI-модели" : "Ответ внешней AI-модели"}</div>}
      {!!warnings?.length && <ul className="ha-task-ai-warnings">{warnings.map((warning, index) => <li key={`${index}-${warning}`}>{warning}</li>)}</ul>}
      {stale && <p className="ha-task-info">Карточка изменилась после запроса. Обновите вопросы, чтобы помощник учёл последние правки.</p>}
      {analysisCurrent && analysis && <section className="ha-task-ai-questions" aria-label="Уточняющие вопросы">
        <div className="ha-task-ai-subheading"><h3>{analysis.result.questions.length ? "Уточним детали" : "Дополнительных вопросов нет"}</h3><p>{analysis.result.questions.length ? "Если ответа пока нет, оставьте поле пустым. Недостающие факты не будут придуманы." : "Проверьте сведения: можно собрать предварительную карточку или продолжить редактирование вручную."}</p></div>
        {analysis.result.questions.map((question, index) => <div className="ha-task-field" key={question.id}><label htmlFor={`ai-answer-${index}`}><span className="ha-task-ai-question-number">{index + 1}</span>{question.question}</label><Textarea id={`ai-answer-${index}`} value={answers[question.id] ?? ""} onChange={(event) => changeAnswer(question.id, event.target.value)} maxLength={question.field === "title" ? 200 : question.field === "contact" ? 500 : 6000} rows={2} disabled={disabled || !!busy} placeholder="Ваш ответ" /></div>)}
        <Button type="button" className="ha-task-primary" onClick={() => void run("build")} disabled={disabled || !!busy}>{busy === "build" ? <Loader2 size={16} className="ha-task-spin" /> : <FileText size={16} />}Собрать предварительную карточку</Button>
      </section>}
      {proposalCurrent && proposal && <section className="ha-task-ai-proposal" aria-label="Предварительная карточка">
        <div className="ha-task-ai-subheading"><h3>Проверьте предложенную карточку</h3><p>Существующие сведения сохранены. Рядом с заполненными полями — цитаты, из которых собран текст.</p></div>
        <dl className="ha-task-ai-preview">{FIELD_KEYS.map((key) => <div key={key} className="ha-task-ai-preview-field"><dt>{FIELD_LABELS[key]}</dt><dd>{proposal.result.fields[key].trim() || <span className="ha-task-empty-value">Пока не указано</span>}</dd>{!!proposal.result.sources[key]?.length && <details className="ha-task-ai-sources"><summary>Источники · {proposal.result.sources[key].length}</summary>{proposal.result.sources[key].map((source, index) => <blockquote key={`${source.sourceId}-${index}`}><span>{sourceLabel(source.sourceId)}</span><p>«{source.quote}»</p></blockquote>)}</details>}</div>)}</dl>
        <Button type="button" className="ha-task-primary" onClick={applyProposal} disabled={disabled || !!busy || applied}><ArrowDownToLine size={16} />Перенести в карточку</Button>
        <p className="ha-task-footnote">Перенос не подтверждает и не публикует задачу. Дальше можно изменить любое поле и сохранить черновик.</p>
      </section>}
      {applied && <p className="ha-task-ai-applied" role="status"><Check size={17} />Сведения перенесены. Проверьте поля ниже и подтвердите карточку перед публикацией.</p>}
      {error && <div className="ha-task-ai-error"><p className="ha-task-error" role="alert">{error}</p>{failedAction && <Button type="button" variant="outline" size="sm" onClick={() => void run(stale ? "analyze" : failedAction)} disabled={disabled || !!busy}><RotateCcw size={14} />Повторить запрос</Button>}</div>}
    </CollapsibleContent>
  </Collapsible>;
}
