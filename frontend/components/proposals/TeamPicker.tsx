"use client";

import { useEffect, useId, useState } from "react";
import { Loader2, RotateCcw, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import type { Team } from "@/lib/contracts";

export default function TeamPicker({ value, onChange, disabled = false }: { value: string; onChange: (id: string) => void; disabled?: boolean }) {
  const id = useId();
  const [retry, setRetry] = useState(0);
  const [result, setResult] = useState<{ key: number; teams: Team[]; error: string } | null>(null);
  const loading = result?.key !== retry;
  const teams = loading ? [] : result.teams;
  const error = loading ? "" : result.error;
  const selected = teams.find((team) => team.id === value);
  useEffect(() => {
    let cancelled = false;
    api.teams().then((data) => { if (!cancelled) setResult({ key: retry, teams: data, error: "" }); }).catch((cause) => { if (!cancelled) setResult({ key: retry, teams: [], error: cause instanceof Error ? cause.message : "Не удалось загрузить команды." }); });
    return () => { cancelled = true; };
  }, [retry]);
  return <section className="alem-team-picker" aria-label="Выбор тестовой команды">
    <label htmlFor={id}><Users size={17} />Тестовая команда для отклика</label>
    {loading ? <p className="alem-proposal-loading" role="status"><Loader2 size={16} className="ha-task-spin" />Загружаем команды…</p> : error ? <div className="alem-proposal-error" role="alert"><p>{error}</p><Button type="button" variant="outline" size="sm" onClick={() => setRetry((current) => current + 1)} disabled={disabled}><RotateCcw size={14} />Повторить</Button></div> : <Select value={selected ? value : ""} onValueChange={onChange} disabled={disabled || !teams.length}><SelectTrigger id={id}><SelectValue placeholder="Выберите команду" /></SelectTrigger><SelectContent>{teams.map((team) => <SelectItem key={team.id} value={team.id}>{team.name}</SelectItem>)}</SelectContent></Select>}
    {!loading && !error && !teams.length && <p className="alem-proposal-muted">Тестовые команды пока не добавлены.</p>}
    <p className="alem-proposal-hint">Команды отдельны от личных профилей студентов. Выберите, от чьего имени отправить предложение.</p>
    {selected && <div className="alem-team-summary"><strong>{selected.name}</strong><div className="alem-proposal-tags">{selected.skills.map((skill) => <span key={skill}>{skill}</span>)}</div><p><span>Технологии:</span> {selected.technologies.join(", ") || "Не указаны"}</p><p><span>Интересы:</span> {selected.interests.join(", ") || "Не указаны"}</p></div>}
  </section>;
}
