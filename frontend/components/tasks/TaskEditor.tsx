"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowLeft, ArrowRight, Check, ChevronRight, Loader2, Save, ScanText, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { api } from "@/lib/api";
import { EMPTY_FIELDS, SKILLS, TOPICS, type Rating, type Task, type TaskFields, type TaskInput } from "@/lib/contracts";
import RatingPanel from "./RatingPanel";
import { FieldQualityHint } from "./QualityReview";
import AIAssistant from "./AIAssistant";
import DescriptionExpander from "./DescriptionExpander";
import qualityStyles from "./quality.module.css";

type Props = { task: Task | null; onClose: () => void; onSaved: (task: Task) => void; onDirtyChange?: (dirty: boolean) => void; onBusyChange?: (busy: boolean) => void };
const STEPS = ["Основа задачи", "Аудитория и данные", "Результат", "Условия и связь"];
const STEP_DESCRIPTIONS = [
  "Опишите ситуацию и задачу, которую вы хотите решить вместе с командой.",
  "Помогите команде понять, для кого создаётся решение и с чем предстоит работать.",
  "Сформулируйте, что вы хотите получить и как будете проверять результат.",
  "Обозначьте границы проекта и договорённости для совместной работы.",
];

function fingerprint(input: TaskInput) {
  return JSON.stringify({
    fields: (Object.keys(EMPTY_FIELDS) as (keyof TaskFields)[]).map((key) => input.fields[key]),
    company: input.company,
    topic: input.topic,
    requiredSkills: [...input.requiredSkills].sort(),
  });
}

export default function TaskEditor(props: Props) {
  return <TaskEditorForm key={`${props.task?.id ?? "new"}:${props.task?.revision ?? 0}`} {...props} />;
}

function TaskEditorForm({ task, onClose, onSaved, onDirtyChange, onBusyChange }: Props) {
  const [fields, setFields] = useState<TaskFields>(() => ({ ...(task?.fields ?? EMPTY_FIELDS) }));
  const [company, setCompany] = useState(task?.company ?? "");
  const [topic, setTopic] = useState(task?.topic ?? "");
  const [skills, setSkills] = useState<string[]>(task?.requiredSkills ?? []);
  const [step, setStep] = useState(0);
  const [confirmed, setConfirmed] = useState(false);
  const [saving, setSaving] = useState<"draft" | "publish" | null>(null);
  const [savePhase, setSavePhase] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<Rating | null>(task?.previewRating ?? null);
  const [previewPending, setPreviewPending] = useState(true);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [semanticStatus, setSemanticStatus] = useState<{ configured: boolean; model: string } | null>(null);
  const [semanticStatusError, setSemanticStatusError] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const reviewLock = useRef(false);
  const [baseline, setBaseline] = useState(() => fingerprint({ fields: task?.fields ?? EMPTY_FIELDS, company: task?.company ?? "", topic: task?.topic ?? "", requiredSkills: task?.requiredSkills ?? [] }));
  const [exitOpen, setExitOpen] = useState(false);
  const [aiPending, setAiPending] = useState(false);
  const [assistantBusy, setAssistantBusy] = useState(false);
  const [contextExpanding, setContextExpanding] = useState(false);
  const [contextExpansionDirty, setContextExpansionDirty] = useState(false);
  const savedId = useRef<string | null>(task?.id ?? null);
  const savingLock = useRef(false);
  const requestVersion = useRef(0);
  const mounted = useRef(true);
  const reportedDirty = useRef<boolean | null>(null);
  const reportedBusy = useRef<boolean | null>(null);
  const busyCallback = useRef(onBusyChange);
  const operationBusy = !!saving || reviewing || assistantBusy || contextExpanding;
  const dirty = aiPending || contextExpansionDirty || fingerprint({ fields, company, topic, requiredSkills: skills }) !== baseline;

  useEffect(() => {
    if (reportedDirty.current !== dirty) {
      reportedDirty.current = dirty;
      onDirtyChange?.(dirty);
    }
  }, [dirty, onDirtyChange]);

  useEffect(() => { busyCallback.current = onBusyChange; }, [onBusyChange]);
  useEffect(() => {
    if (reportedBusy.current !== operationBusy) { reportedBusy.current = operationBusy; onBusyChange?.(operationBusy); }
  }, [operationBusy, onBusyChange]);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; requestVersion.current += 1; busyCallback.current?.(false); };
  }, []);

  useEffect(() => {
    let cancelled = false;
    api.ratingStatus().then((status) => { if (!cancelled) setSemanticStatus(status); })
      .catch(() => { if (!cancelled) setSemanticStatusError(true); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const version = ++requestVersion.current;
    const timer = window.setTimeout(async () => {
      try {
        const result = await api.previewRating(fields);
        if (version === requestVersion.current && mounted.current) setPreview(result);
      } catch {
        if (version === requestVersion.current && mounted.current) {
          setPreviewError("Не удалось рассчитать рейтинг. Измените поле, чтобы повторить попытку.");
        }
      } finally {
        if (version === requestVersion.current && mounted.current) setPreviewPending(false);
      }
    }, 350);
    return () => { window.clearTimeout(timer); requestVersion.current += 1; };
  }, [fields]);

  function changed() { setConfirmed(false); setError(null); }
  function updateField(key: keyof TaskFields, value: string) {
    requestVersion.current += 1;
    setPreviewPending(true);
    setPreviewError(null);
    setReviewError(null);
    setFields((current) => ({ ...current, [key]: value }));
    changed();
  }
  function toggleSkill(skill: string) {
    setSkills((current) => current.includes(skill) ? current.filter((item) => item !== skill) : [...current, skill]);
    changed();
  }
  function applyAIFields(proposedFields: TaskFields, expectedSnapshot: string) {
    if (savingLock.current || reviewLock.current || contextExpanding || fingerprint({ fields, company, topic, requiredSkills: skills }) !== expectedSnapshot) return false;
    requestVersion.current += 1;
    setPreviewPending(true);
    setPreviewError(null);
    setReviewError(null);
    setFields({ ...proposedFields });
    setStep(0);
    changed();
    return true;
  }
  async function reviewMeaning() {
    if (reviewLock.current || savingLock.current || assistantBusy || contextExpanding || previewPending) return;
    reviewLock.current = true;
    const version = ++requestVersion.current;
    setReviewing(true);
    setReviewError(null);
    try {
      const result = await api.reviewRating(fields);
      if (mounted.current && version === requestVersion.current) {
        setPreview(result);
        setPreviewError(null);
      }
    } catch (cause) {
      if (mounted.current && version === requestVersion.current) {
        setReviewError(cause instanceof Error ? cause.message : "Не удалось проверить смысл. Повторите попытку.");
      }
    } finally {
      reviewLock.current = false;
      if (mounted.current) setReviewing(false);
    }
  }
  function markSaved(input: TaskInput) {
    setBaseline(fingerprint(input));
    if (reportedDirty.current !== aiPending) {
      reportedDirty.current = aiPending;
      onDirtyChange?.(aiPending);
    }
  }
  function requestClose() {
    if (savingLock.current || operationBusy) return;
    if (dirty) setExitOpen(true);
    else onClose();
  }
  function discardAndClose() {
    if (savingLock.current || operationBusy) return;
    reportedDirty.current = false;
    onDirtyChange?.(false);
    onClose();
  }

  async function save(publish: boolean) {
    if (savingLock.current) return;
    if (assistantBusy || contextExpanding) { setError("Дождитесь завершения работы AI-помощника перед сохранением."); return; }
    if (reviewLock.current) { setError("Дождитесь завершения AI-проверки перед сохранением."); return; }
    if (publish && !confirmed) { setError("Подтвердите сведения в карточке перед публикацией."); return; }
    if (publish && !fields.title.trim()) { setStep(0); setError("Для публикации укажите название задачи."); return; }
    savingLock.current = true;
    setSaving(publish ? "publish" : "draft");
    setSavePhase("Сохраняем карточку…");
    setError(null);
    const input: TaskInput = { fields, company, topic, requiredSkills: skills };
    let saved = false;
    try {
      let result = savedId.current ? await api.updateTask(savedId.current, input) : await api.createTask(input);
      savedId.current = result.id;
      saved = true;
      if (publish) {
        setSavePhase(semanticStatus?.configured ? "Проверяем смысл с AI и подтверждаем сведения…" : "Подтверждаем сведения…");
        result = await api.confirmTask(result.id);
        setSavePhase("Публикуем в каталоге…");
        result = await api.publishTask(result.id);
      }
      if (mounted.current) { markSaved(input); onSaved(result); }
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Проверьте соединение с сервером и попробуйте ещё раз.";
      if (mounted.current) {
        if (saved) markSaved(input);
        setError(saved
          ? `Черновик сохранён, но не удалось подтвердить завершение публикации. ${message}`
          : `Не удалось сохранить задачу. ${message}`);
      }
    } finally {
      savingLock.current = false;
      if (mounted.current) { setSaving(null); setSavePhase(""); }
    }
  }

  function textField(key: keyof TaskFields, label: string, placeholder: string, hint?: string) {
    const quality = !previewPending && !previewError ? preview?.quality?.fields.find((item) => item.field === key) : undefined;
    return <div className="ha-task-field" key={key}>
      <label htmlFor={`task-${key}`}>{label}</label>
      <Textarea id={`task-${key}`} value={fields[key]} onChange={(event) => updateField(key, event.target.value)} placeholder={placeholder} rows={3} maxLength={6000} disabled={!!saving || assistantBusy || contextExpanding} aria-describedby={quality && quality.status !== "missing" ? `quality-${key}` : undefined} />
      {key === "context" && <DescriptionExpander source={fields.context} disabled={!!saving || reviewing || assistantBusy} onBusyChange={setContextExpanding} onDirtyChange={setContextExpansionDirty} onApply={(value, expectedSource) => {
        if (savingLock.current || reviewLock.current || assistantBusy || fields.context !== expectedSource) return false;
        updateField("context", value);
        return true;
      }} />}
      {hint && <p className="ha-task-field-hint">{hint}</p>}
      <FieldQualityHint result={quality} id={`quality-${key}`} />
    </div>;
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (step < STEPS.length - 1) setStep((current) => current + 1);
    else void save(true);
  }

  return <div className="ha-task-editor">
    <Button className="ha-task-back" variant="ghost" onClick={requestClose} disabled={operationBusy}><ArrowLeft size={16} /> К моим задачам</Button>
    <header className="ha-task-page-heading">
      <div><div className="ha-task-eyebrow">Для бизнеса</div><h1>{task ? "Редактирование задачи" : "Новая задача"}</h1><p>Хорошее описание — первый шаг к сильному решению.</p></div>
      <span className="ha-task-draft-badge">{task?.published ? "Изменения карточки" : "Черновик"}</span>
    </header>
    {task?.published && <div className="ha-task-info">В каталоге остаётся опубликованная версия. Обновления появятся после повторного подтверждения и публикации.</div>}
    <div className="ha-task-editor-layout">
      <form onSubmit={handleSubmit} className="ha-task-form-column">
        <AIAssistant fields={fields} formSnapshot={fingerprint({ fields, company, topic, requiredSkills: skills })} disabled={!!saving || reviewing || contextExpanding} onApply={applyAIFields} onDirtyChange={setAiPending} onBusyChange={setAssistantBusy} onSourceChange={changed} />
        <nav className="ha-task-step-nav" aria-label="Разделы карточки">
          {STEPS.map((label, index) => <Button type="button" variant="ghost" key={label} disabled={operationBusy} onClick={() => setStep(index)} className={`ha-task-step ${step === index ? "ha-task-step-active" : ""}`} aria-current={step === index ? "step" : undefined}><span>{index + 1}</span><span>{label}</span></Button>)}
        </nav>
        <section className="ha-task-card ha-task-form-card" aria-labelledby="task-step-title">
          <div className="ha-task-section-heading"><span className="ha-task-section-number">0{step + 1}</span><div><h2 id="task-step-title">{STEPS[step]}</h2><p>{STEP_DESCRIPTIONS[step]}</p></div></div>
          {step === 0 && <div className="ha-task-fields">
            <div className="ha-task-field"><label htmlFor="task-title">Название задачи <span className="ha-task-optional">нужно для публикации</span></label><Input id="task-title" value={fields.title} onChange={(event) => updateField("title", event.target.value)} placeholder="Например, бот для вопросов клиентов" maxLength={200} disabled={operationBusy} /></div>
            <div className="ha-task-two-columns">
              <div className="ha-task-field"><label htmlFor="task-company">Компания</label><Input id="task-company" value={company} onChange={(event) => { setCompany(event.target.value); changed(); }} placeholder="Название компании" maxLength={160} disabled={operationBusy} /></div>
              <div className="ha-task-field"><label htmlFor="task-topic">Направление</label><Select value={topic} onValueChange={(value) => { setTopic(value === "__none__" ? "" : value); changed(); }} disabled={operationBusy}><SelectTrigger id="task-topic"><SelectValue placeholder="Выберите направление" /></SelectTrigger><SelectContent><SelectItem value="__none__">Не указано</SelectItem>{topic && !TOPICS.includes(topic) && <SelectItem value={topic}>{topic}</SelectItem>}{TOPICS.slice(1).map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}</SelectContent></Select></div>
            </div>
            <div className="ha-task-field"><span className="ha-task-label">Навыки команды <span className="ha-task-optional">необязательно</span></span><div className="ha-task-skills" role="group" aria-label="Требуемые навыки">{Array.from(new Set([...SKILLS, ...skills])).map((skill) => <Button type="button" size="sm" variant="outline" key={skill} aria-pressed={skills.includes(skill)} className={`ha-task-skill ${skills.includes(skill) ? "ha-task-skill-selected" : ""}`} onClick={() => toggleSkill(skill)} disabled={operationBusy}>{skills.includes(skill) && <Check size={13} />}{skill}</Button>)}</div><p className="ha-task-field-hint">По этим навыкам студенты смогут найти подходящий квест.</p></div>
            {textField("context", "Что происходит сейчас", "Опишите текущий процесс и проблему.")}
            {textField("need", "Что нужно изменить", "Какую задачу вы хотите решить?")}
          </div>}
          {step === 1 && <div className="ha-task-fields">
            {textField("users", "Для кого создаётся решение", "Кто будет пользоваться результатом? Какую задачу решают эти люди?")}
            {textField("data", "Данные и материалы", "Какие данные, примеры или источники доступны команде?", "Можно указать формат, объём и условия доступа. Если данных пока нет, напишите об этом.")}
          </div>}
          {step === 2 && <div className="ha-task-fields">
            {textField("expectedResult", "Ожидаемый результат", "Например, прототип бота с ответами на 20 частых вопросов.")}
            {textField("successCriteria", "Как поймём, что задача решена", "По каким измеримым признакам вы примете результат?", "Например: корректный ответ минимум на 8 из 10 тестовых обращений.")}
          </div>}
          {step === 3 && <div className="ha-task-fields">
            {textField("constraints", "Ограничения", "Сроки, технологии, доступы и другие условия.")}
            <div className="ha-task-field"><label htmlFor="task-contact">Контакт представителя бизнеса</label><Input id="task-contact" value={fields.contact} onChange={(event) => updateField("contact", event.target.value)} placeholder="Имя и рабочий email или Telegram" maxLength={500} disabled={operationBusy} /></div>
            <div className="ha-task-two-columns">
              {textField("interactionFormat", "Консультации и обратная связь", "Как вы будете общаться, проверять результат и отвечать команде?")}
              {textField("feedbackProcess", "Дополнительные договорённости", "Кто проверяет результат и когда отвечает?", "Необязательно. Это поле не влияет на рейтинг.")}
            </div>
          </div>}
          <div className="ha-task-step-footer"><span>Шаг {step + 1} из {STEPS.length}</span><div>{step > 0 && <Button type="button" variant="ghost" onClick={() => setStep((current) => current - 1)} disabled={operationBusy}><ArrowLeft size={15} /> Назад</Button>}{step < STEPS.length - 1 && <Button type="button" variant="outline" onClick={() => setStep((current) => current + 1)} disabled={operationBusy}>Далее <ChevronRight size={16} /></Button>}</div></div>
        </section>
        {step === 3 && <div className="ha-task-card ha-task-confirmation"><Checkbox id="task-confirmation" checked={confirmed} onCheckedChange={(value) => setConfirmed(value === true)} disabled={operationBusy} /><label htmlFor="task-confirmation"><strong>Я проверил(а) сведения в карточке</strong><span>Подтверждаю текущую версию. После публикации она будет доступна всем студентам.</span></label></div>}
        {error && <p role="alert" className="ha-task-error ha-task-save-error">{error}</p>}
        {aiPending && <p className="ha-task-info">Описание и ответы помощнику ещё не перенесены в карточку. Сохранение или публикация сохранят только поля карточки; ввод помощнику будет потерян после закрытия редактора. Сначала нажмите «Перенести в карточку», если хотите его использовать.</p>}
        <div className="ha-task-form-actions"><Button type="button" variant="outline" onClick={() => void save(false)} disabled={operationBusy}>{saving === "draft" ? <Loader2 size={16} className="ha-task-spin" /> : <Save size={16} />} Сохранить черновик</Button>{step === 3 ? <Button className="ha-task-primary" type="submit" disabled={operationBusy || !confirmed}>{saving === "publish" ? <Loader2 size={16} className="ha-task-spin" /> : <Send size={16} />}{task?.published ? "Обновить публикацию" : "Опубликовать задачу"}</Button> : <Button className="ha-task-primary" type="submit" disabled={operationBusy}>Следующий шаг <ArrowRight size={16} /></Button>}</div>
        {saving && <p className="ha-task-inline-status" role="status">{savePhase}</p>}
        <p className="ha-task-footnote">Не всё известно? Сохраните черновик или опубликуйте задачу с неполным описанием. Рейтинг подскажет, что можно дополнить.</p>
      </form>
      <aside className="ha-task-rating-column">
        <div className={qualityStyles.aiControl}>
          <strong><ScanText size={17} /> Проверка смысла</strong>
          <p>{semanticStatus?.configured ? "AI проверяет содержание и связь разделов. При публикации проверка обязательна; исправленный текст оценивается заново." : semanticStatusError ? "Не удалось узнать состояние AI. Повторите открытие редактора." : semanticStatus ? "AI пока не подключён. Ниже — предварительная проверка по правилам, она не заменяет оценку смысла." : "Проверяем подключение AI…"}</p>
          <Button type="button" variant="outline" onClick={() => void reviewMeaning()} disabled={!semanticStatus?.configured || operationBusy || previewPending}>
            {reviewing ? <Loader2 size={16} className="ha-task-spin" /> : <ScanText size={16} />}{reviewing ? "Проверяем смысл…" : "Проверить смысл с AI"}
          </Button>
          {semanticStatus?.configured && <small>Во внешний AI отправляется текст карточки; контактное поле и файлы не передаются. Запросы используют ваш API.</small>}
          {reviewError && <p role="alert" className="ha-task-error">{reviewError} Предварительные баллы ниже не означают, что AI одобрил описание.</p>}
        </div>
        <RatingPanel rating={preview} preview loading={previewPending || reviewing} error={previewError} />
      </aside>
    </div>
    <AlertDialog open={exitOpen} onOpenChange={setExitOpen}>
      <AlertDialogContent className="ha-task-exit-dialog">
        <AlertDialogHeader><AlertDialogTitle>Выйти без сохранения?</AlertDialogTitle><AlertDialogDescription>{aiPending ? "В помощнике есть описание или ответы, которые ещё не перенесены в карточку. При выходе они будут потеряны. Вернитесь, чтобы перенести сведения и сохранить черновик." : "В карточке есть несохранённые изменения. Можно вернуться к редактированию и сохранить черновик."}</AlertDialogDescription></AlertDialogHeader>
        <AlertDialogFooter><AlertDialogCancel>Продолжить редактирование</AlertDialogCancel><AlertDialogAction onClick={discardAndClose}>Выйти без сохранения</AlertDialogAction></AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>;
}
