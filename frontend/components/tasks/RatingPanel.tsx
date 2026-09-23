"use client";

import { Check, CircleHelp, Loader2, Sparkles } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { LEVELS, type Rating } from "@/lib/contracts";

export const FIELD_LABELS: Record<string, string> = {
  title: "Название", context: "Контекст", need: "Потребность", users: "Пользователи",
  data: "Данные и материалы", constraints: "Ограничения", expectedResult: "Ожидаемый результат",
  successCriteria: "Критерии успеха", contact: "Контакт", interactionFormat: "Консультации и обратная связь",
  feedbackProcess: "Дополнительные договорённости",
};

export default function RatingPanel({ rating, preview = false, loading = false, error }: {
  rating: Rating | null; preview?: boolean; loading?: boolean; error?: string | null;
}) {
  const available = rating !== null && !loading && !error;
  const suggestions = rating ? Array.from(new Set(rating.breakdown.flatMap((item) => item.missing))) : [];
  return (
    <section className="ha-task-card ha-task-rating" aria-label="Готовность описания" aria-busy={loading}>
      <div className="ha-task-eyebrow"><Sparkles size={15} /> Готовность описания</div>
      <div className="ha-task-score-line">
        <strong>{available ? rating.score : "—"}<small> / 100</small></strong>
        {available && <span className={`ha-task-level ha-task-level-${rating.level}`}>{LEVELS[rating.level].label}</span>}
      </div>
      <Progress value={available ? rating.score : 0} aria-label="Рейтинг готовности" className="ha-task-progress" />
      <p className="ha-task-muted ha-task-rating-note">
        {preview ? "После подтверждения" : "Начисленные баллы"}
      </p>
      {loading && <p className="ha-task-inline-status" role="status"><Loader2 size={15} className="ha-task-spin" /> Пересчитываем рейтинг…</p>}
      {error && <p className="ha-task-error" role="alert">{error}</p>}
      {available && <>
        <div className="ha-task-rating-items">
          {rating.breakdown.map((item) => (
            <div className="ha-task-rating-item" key={item.key}>
              <span>{item.earned === item.max ? <Check size={15} className="ha-task-complete" /> : <CircleHelp size={15} />}{item.label}</span>
              <strong>{item.earned}<small> / {item.max}</small></strong>
            </div>
          ))}
        </div>
        <div className="ha-task-rating-tip">
          <strong>{rating.missingFields.length ? "Что улучшить" : "Все разделы заполнены"}</strong>
          {rating.missingFields.length ? <ul>{(suggestions.length ? suggestions : rating.missingFields.map((field) => FIELD_LABELS[field] ?? field)).map((suggestion) => <li key={suggestion}>{suggestion}</li>)}</ul> : <p>Все сведения, влияющие на рейтинг, заполнены.</p>}
        </div>
      </>}
      <p className="ha-task-footnote">Баллы отражают полноту описания. Задача с любым рейтингом может попасть в каталог.</p>
    </section>
  );
}
