"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDownLeft, ArrowUpRight, Check, Coins, Gift, Home, Loader2, Paintbrush, RotateCcw, Sparkles, Trophy } from "lucide-react";
import TeamPicker from "@/components/proposals/TeamPicker";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { RewardItem, TeamRewards } from "@/lib/contracts";
import RoomScene from "./RoomScene";
import styles from "./rewards.module.css";

type Props = { teamId: string; onTeamChange: (id: string) => void; onBusyChange: (busy: boolean) => void; onCatalog: () => void };
const SLOT_LABELS: Record<RewardItem["slot"], string> = { background: "Фон профиля", poster: "Постер", plant: "Растение", lamp: "Освещение" };

export default function RewardsPage({ teamId, onTeamChange, onBusyChange, onCatalog }: Props) {
  const [busy, setBusy] = useState(false);
  function reportBusy(value: boolean) { setBusy(value); onBusyChange(value); }
  return <div className={styles.page}>
    <div className="page-heading"><div><div className="eyebrow">РЕЗУЛЬТАТЫ СТАНОВЯТСЯ НАГРАДАМИ</div><h1>Пространство <em className="hero-emphasis">команды</em><span className="heading-dot">.</span></h1><p>Завершайте проекты, получайте баллы и обустраивайте своё место для новых идей.</p></div><Button type="button" variant="outline" disabled={busy} onClick={onCatalog}>К каталогу задач</Button></div>
    <div className={styles.teamPicker}><TeamPicker value={teamId} onChange={onTeamChange} disabled={busy} purpose="rewards" /></div>
    {teamId ? <TeamSpace key={teamId} teamId={teamId} onBusyChange={reportBusy} /> : <div className={styles.empty}><Home size={34} /><h2>У каждой команды — своё пространство</h2><p>Выберите команду, чтобы увидеть её баллы, коллекцию и виртуальную комнату.</p></div>}
  </div>;
}

function TeamSpace({ teamId, onBusyChange }: { teamId: string; onBusyChange: (busy: boolean) => void }) {
  const [retry, setRetry] = useState(0);
  const [result, setResult] = useState<{ key: number; data: TeamRewards | null; error: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const mounted = useRef(true);
  const lock = useRef(false);
  const loading = result?.key !== retry;
  const data = loading ? null : result.data;
  const error = loading ? "" : result.error;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    let cancelled = false;
    api.teamRewards(teamId).then((data) => { if (!cancelled) setResult({ key: retry, data, error: "" }); }).catch((cause) => { if (!cancelled) setResult({ key: retry, data: null, error: cause instanceof Error ? cause.message : "Не удалось загрузить награды команды." }); });
    return () => { cancelled = true; };
  }, [teamId, retry]);

  async function act(item: RewardItem, operation: "purchase" | "equip" | "remove") {
    if (lock.current) return;
    lock.current = true;
    setBusy(item.id);
    setActionError("");
    setNotice("");
    onBusyChange(true);
    try {
      const updated = operation === "purchase" ? await api.purchaseReward(teamId, item.id) : await api.equipReward(teamId, item.slot, operation === "remove" ? null : item.id);
      if (mounted.current) {
        setResult({ key: retry, data: updated, error: "" });
        setNotice(operation === "purchase" ? `«${item.name}» в вашей коллекции. Нажмите «Применить», чтобы изменить пространство.` : operation === "remove" ? `«${item.name}» снято. Предмет остаётся в вашей коллекции.` : `«${item.name}» применено к пространству команды.`);
      }
    } catch (cause) { if (mounted.current) setActionError(cause instanceof Error ? cause.message : "Не удалось сохранить изменение. Обновите баланс и попробуйте снова."); }
    finally { lock.current = false; if (mounted.current) { setBusy(null); onBusyChange(false); } }
  }

  if (loading) return <p className={styles.loading} role="status"><Loader2 className="ha-task-spin" size={20} />Загружаем пространство команды…</p>;
  if (error || !data) return <div className={styles.empty} role="alert"><p>{error || "Данные команды недоступны."}</p><Button type="button" variant="outline" onClick={() => setRetry((value) => value + 1)}><RotateCcw size={15} />Повторить загрузку</Button></div>;
  const owned = new Set(data.ownedItemIds);
  const nextReward = data.items.filter((item) => !owned.has(item.id)).sort((a, b) => a.cost - b.cost)[0];
  const currentStyle = (slot: RewardItem["slot"]) => data.items.find((item) => item.id === data.equipped[slot])?.style;
  const background = currentStyle("background");
  const poster = currentStyle("poster");
  const remaining = nextReward ? Math.max(0, nextReward.cost - data.balance) : 0;
  const progress = nextReward ? Math.min(100, Math.round(data.balance / nextReward.cost * 100)) : 100;

  return <>
    <section className={`${styles.profile} ${background === "night" ? styles.night : background === "dawn" ? styles.dawn : ""}`} aria-label="Профиль и комната команды">
      <div className={styles.roomColumn}><div className={styles.profileHeading}><span><Home size={16} />Виртуальная комната</span><span className={styles.collectionCount}>{owned.size} / {data.items.length} предметов</span></div><RoomScene background={background} poster={poster} plant={!!data.equipped.plant} lamp={!!data.equipped.lamp} /><div className={styles.roomCaption}><span><Sparkles size={14} />Ваше место для больших идей</span><small>{background ? "Купленный фон применён к профилю" : "Базовая комната и фон — бесплатно"}</small></div></div>
      <div className={styles.wallet}><div className={styles.walletHeading}><span><Coins size={18} />Баланс команды</span><Button type="button" variant="ghost" size="icon" aria-label="Обновить баланс" disabled={!!busy} onClick={() => { setNotice(""); setActionError(""); setRetry((value) => value + 1); }}><RotateCcw size={16} /></Button></div><div className={styles.balance}><strong>{data.balance.toLocaleString("ru")}</strong><span>баллов</span></div><div className={styles.stats}><div><Trophy size={17} /><strong>{data.completedProjects}</strong><span>Проектов завершено</span></div><div><Sparkles size={17} /><strong>{data.totalEarned.toLocaleString("ru")}</strong><span>Всего заработано</span></div></div>
        <div className={styles.nextReward}><span>{nextReward ? remaining ? "До следующей награды" : "Награда уже доступна" : "Коллекция собрана"}</span><strong>{nextReward ? nextReward.name : "Все предметы у команды"}</strong><div className={styles.progress} role="progressbar" aria-label={nextReward ? `Баллы на награду «${nextReward.name}»` : "Коллекция собрана"} aria-valuemin={0} aria-valuemax={nextReward?.cost ?? 100} aria-valuenow={nextReward ? Math.min(data.balance, nextReward.cost) : 100}><span style={{ width: `${progress}%` }} /></div><small>{nextReward ? remaining ? `Осталось ${remaining} баллов из ${nextReward.cost}` : `Можно обменять ${nextReward.cost} баллов в магазине` : "Меняйте оформление в любое время"}</small></div>
      </div>
    </section>
    <div className={styles.rule}><div className={styles.ruleIcon}><Trophy size={20} /></div><p><strong>+100 баллов за завершённый проект</strong><span>Бизнес проверяет результат выбранной команды и подтверждает завершение. Награда начисляется один раз за пару «команда + задача». Покупки меняют оформление профиля и комнаты, а рейтинг бизнес-задач остаётся прежним.</span></p></div>
    {actionError && <div className={styles.error} role="alert"><p>{actionError}</p><Button type="button" variant="outline" size="sm" disabled={!!busy} onClick={() => { setActionError(""); setRetry((value) => value + 1); }}>Обновить баланс</Button></div>}
    {notice && <p className={styles.notice} role="status"><Check size={17} />{notice}</p>}
    <section className={styles.shop} aria-labelledby="rewards-shop-title"><div className={styles.sectionHeading}><div><span className={styles.kicker}>МАЛЕНЬКИЕ ДЕТАЛИ, ВАШ ХАРАКТЕР</span><h2 id="rewards-shop-title">Магазин наград</h2><p>Один раз получаете предмет — используете сколько угодно.</p></div><span className={styles.shopBadge}><Gift size={15} />Обмен за баллы</span></div><div className={styles.items}>{data.items.map((item) => {
      const isOwned = owned.has(item.id);
      const equipped = data.equipped[item.slot] === item.id;
      const affordable = data.balance >= item.cost;
      return <article className={`${styles.item} ${equipped ? styles.equipped : ""}`} key={item.id}><div className={styles.preview}><RoomScene background={item.slot === "background" ? item.style : undefined} poster={item.slot === "poster" ? item.style : undefined} plant={item.slot === "plant"} lamp={item.slot === "lamp"} />{isOwned && <span className={styles.ownedBadge}><Check size={12} />{equipped ? "Применено" : "В коллекции"}</span>}</div><div className={styles.itemContent}><span className={styles.itemSlot}>{SLOT_LABELS[item.slot]}</span><h3>{item.name}</h3><p>{item.description}</p><div className={styles.itemFooter}><span className={styles.cost}><Coins size={16} />{item.cost}<small>баллов</small></span>{isOwned ? <Button type="button" variant={equipped ? "outline" : "default"} className={equipped ? "" : "ha-task-primary"} disabled={!!busy} onClick={() => void act(item, equipped ? "remove" : "equip")}>{busy === item.id ? <Loader2 className="ha-task-spin" size={14} /> : equipped ? <Check size={14} /> : <Paintbrush size={14} />}{equipped ? "Снять" : "Применить"}</Button> : <Button type="button" variant={affordable ? "default" : "outline"} className={affordable ? "ha-task-primary" : ""} disabled={!!busy || !affordable} onClick={() => void act(item, "purchase")} aria-label={`Купить «${item.name}» за ${item.cost} баллов`}>{busy === item.id ? <Loader2 className="ha-task-spin" size={14} /> : <Gift size={14} />}Купить</Button>}</div>{!isOwned && !affordable && <small className={styles.shortfall}>Не хватает {item.cost - data.balance} баллов</small>}</div></article>;
    })}</div></section>
    <section className={styles.history} aria-labelledby="rewards-history-title"><div className={styles.sectionHeading}><div><span className={styles.kicker}>КАЖДЫЙ РЕЗУЛЬТАТ ИМЕЕТ ЗНАЧЕНИЕ</span><h2 id="rewards-history-title">История баллов</h2></div></div>{data.history.length ? <ol>{data.history.map((entry) => <li key={entry.id}><div className={`${styles.historyIcon} ${entry.amount > 0 ? styles.earnedIcon : ""}`}>{entry.amount > 0 ? <ArrowDownLeft size={20} /> : <ArrowUpRight size={20} />}</div><div className={styles.historyLabel}><strong>{entry.label}</strong><span>{entry.kind === "project_reward" ? "Завершение проекта" : "Обмен на награду"} · {new Intl.DateTimeFormat("ru", { day: "numeric", month: "long", year: "numeric" }).format(new Date(entry.createdAt))}</span></div><strong className={entry.amount > 0 ? styles.positive : styles.negative}>{entry.amount > 0 ? "+" : "−"}{Math.abs(entry.amount)}<small>баллов</small></strong></li>)}</ol> : <div className={styles.historyEmpty}><Coins size={26} /><div><strong>Первый результат — впереди</strong><p>Баллы появятся здесь после того, как бизнес подтвердит успешное завершение проекта.</p></div></div>}</section>
  </>;
}
