import { CheckCircle2, CircleHelp, ScanText } from "lucide-react";
import type { QualityField, QualityReport } from "@/lib/contracts";
import styles from "./quality.module.css";

export function FieldQualityHint({ result, id }: { result?: QualityField; id: string }) {
  if (!result || result.status === "missing") return null;
  return <p id={id} className={`${styles.fieldHint} ${result.status === "ready" ? styles.ready : styles.needsWork}`}>
    {result.status === "ready" ? <CheckCircle2 size={15} aria-hidden="true" /> : <CircleHelp size={15} aria-hidden="true" />}
    <span>{result.message}{result.status === "needs_work" && result.suggestion ? ` ${result.suggestion}` : ""}</span>
  </p>;
}

export default function QualityReview({ report, labels }: { report: QualityReport; labels: Record<string, string> }) {
  const issues = report.fields.filter((item) => item.status !== "ready")
    .sort((a, b) => Number(b.status === "needs_work") - Number(a.status === "needs_work"));
  const needsWork = issues.filter((item) => item.status === "needs_work").length;
  return <div className={styles.review} aria-label="Проверка качества описания">
    <div className={styles.heading}><ScanText size={17} aria-hidden="true" /><strong>Проверка содержания</strong></div>
    <p className={styles.summary}>Достаточно конкретны {report.eligibleFields.length} из {report.fields.length} разделов. Баллы за них начислятся после подтверждения.</p>
    {issues.length > 0 ? <details className={styles.details} open={needsWork > 0}>
      <summary>Что уточнить · {issues.length}</summary>
      <ul className={styles.issues}>{issues.map((item) => <li key={item.field}>
        <strong>{labels[item.field] ?? item.field}</strong>
        <span className={item.status === "needs_work" ? styles.needsWork : ""}>{item.message}</span>
        {item.suggestion && <p>{item.suggestion}</p>}
      </li>)}</ul>
    </details> : <p className={styles.ready}><CheckCircle2 size={15} aria-hidden="true" /> Все оцениваемые поля прошли проверку.</p>}
    <p className={styles.note}>Проверка по правилам помогает найти неточности. Смысл и достоверность сведений подтверждает бизнес.</p>
  </div>;
}
