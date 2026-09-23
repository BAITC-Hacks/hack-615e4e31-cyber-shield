"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import TaskEditor from "@/components/tasks/TaskEditor";
import TaskDetails from "@/components/tasks/TaskDetails";
import { ArrowDownWideNarrow, ArrowRight, Bookmark, BriefcaseBusiness, Check, ChevronRight, CircleHelp, Compass, GraduationCap, LayoutGrid, LoaderCircle, Plus, Search, ShieldCheck, SlidersHorizontal, Sparkles, Target, TrendingUp, X } from "lucide-react";
import { Sidebar, SidebarContent, SidebarFooter, SidebarHeader, SidebarInset, SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarProvider, SidebarTrigger, useSidebar } from "@/components/ui/sidebar";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Toaster, toast } from "sonner";
import { api } from "@/lib/api";
import { LEVELS, SKILLS, TOPICS, type Quest, type Role, type StudentProfile, type Task } from "@/lib/contracts";

type View = "catalog" | "mine" | "saved";
const TOPIC_MARKS: Record<string, string> = { "Торговля": "Т", "Образование": "О", "Сервисы": "С", "Логистика": "Л", "HoReCa": "H" };

export default function Home() {
  const [role, setRole] = useState<Role>("business");
  const [view, setView] = useState<View>("catalog");
  const [profiles, setProfiles] = useState<StudentProfile[]>([]);
  const [profileId, setProfileId] = useState("");
  const [savedTasks, setSavedTasks] = useState<Task[]>([]);
  const [result, setResult] = useState<{key: string; tasks: Task[]; error: string} | null>(null);
  const [search, setSearch] = useState("");
  const [topic, setTopic] = useState("all");
  const [readiness, setReadiness] = useState("all");
  const [profileOpen, setProfileOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [quest, setQuest] = useState<Quest | null>(null);
  const [busy, setBusy] = useState(false);
  const [skillDraft, setSkillDraft] = useState<string[]>([]);
  const [detail, setDetail] = useState<Task | null>(null);
  const [editor, setEditor] = useState<Task | "new" | null>(null);
  const [editorDirty, setEditorDirty] = useState(false);
  const [pendingNavigation, setPendingNavigation] = useState<(() => void) | null>(null);
  const [revision, setRevision] = useState(0);
  const shownQuests = useRef(new Set<string>());
  const profile = profiles.find((item) => item.id === profileId);
  const skillsKey = profile?.skills.join("|") ?? "";
  const requestKey = `${view}:${role}:${revision}:${profileId}`;
  const loading = result?.key !== requestKey;
  const tasks = loading ? [] : result.tasks;
  const error = loading ? "" : result.error;
  const refresh = useCallback(() => setRevision((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    api.profiles().then((data) => { if (!cancelled) { setProfiles(data); setProfileId((current) => data.some((item) => item.id === current) ? current : data[0]?.id ?? ""); } }).catch((err) => { if (!cancelled) toast.error(err.message); });
    return () => { cancelled = true; };
  }, [revision]);

  useEffect(() => {
    let cancelled = false;
    const fetchTasks = view === "saved" && profileId ? api.saved(profileId) : api.listTasks(view === "mine" && role === "business");
    fetchTasks.then((data) => { if (!cancelled) setResult({key: requestKey, tasks: data, error: ""}); }).catch((err) => { if (!cancelled) setResult({key: requestKey, tasks: [], error: err.message}); });
    return () => { cancelled = true; };
  }, [view, role, requestKey, profileId]);

  useEffect(() => {
    if (role !== "student" || !profileId) return;
    let cancelled = false;
    api.saved(profileId).then((data) => { if (!cancelled) setSavedTasks(data); }).catch((err) => { if (!cancelled) toast.error(err.message); });
    return () => { cancelled = true; };
  }, [role, profileId, revision]);

  useEffect(() => {
    if (role !== "student" || !profileId) return;
    let cancelled = false;
    api.quests(profileId).then((data) => {
      if (cancelled) return;
      const next = data.find((item) => !shownQuests.current.has(`${profileId}:${item.task.id}`));
      if (next) { shownQuests.current.add(`${profileId}:${next.task.id}`); setQuest(next); }
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [role, profileId, skillsKey]);

  function leaveEditor(action: () => void) { if (editor && editorDirty) setPendingNavigation(() => action); else action(); }
  function closeEditor() { setEditor(null); setEditorDirty(false); }
  function changeRole(value: string) { leaveEditor(() => { setRole(value as Role); setView("catalog"); setSearch(""); setTopic("all"); setReadiness("all"); setDetail(null); closeEditor(); setQuest(null); }); }
  function navigate(next: View) { leaveEditor(() => { setView(next); closeEditor(); setSearch(""); setTopic("all"); setReadiness("all"); }); }
  async function saveTask(task: Task) {
    if (!profileId) throw new Error("Профиль ещё загружается. Попробуйте снова.");
    await api.decideQuest(task.id, profileId, "saved");
    setSavedTasks((items) => [...items.filter((item) => item.id !== task.id), task]);
    setQuest(null); toast.success("Квест сохранён", { description: "Он доступен в разделе «Мои квесты». Исполнитель ещё не назначен." }); refresh();
  }
  async function decideQuest(decision: "saved" | "dismissed") {
    if (!quest) return;
    setBusy(true);
    try { if (decision === "saved") await saveTask(quest.task); else { await api.decideQuest(quest.task.id, profileId, decision); setQuest(null); toast("Рекомендация отложена", { description: "Задача остаётся в общем каталоге." }); } }
    catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  }
  async function updateSkills() {
    setBusy(true);
    try { const updated = await api.updateSkills(profileId, skillDraft); setProfiles((items) => items.map((item) => item.id === updated.id ? updated : item)); setProfileOpen(false); refresh(); toast.success("Навыки обновлены"); }
    catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  }
  const visible = tasks.filter((task) => (topic === "all" || task.topic === topic) && (readiness === "all" || task.rating.level === readiness) && `${task.fields.title} ${task.company} ${task.fields.need} ${task.requiredSkills.join(" ")}`.toLocaleLowerCase("ru").includes(search.toLocaleLowerCase("ru")));
  const availableTopics = Array.from(new Set([...TOPICS.slice(1), ...tasks.map((task) => task.topic).filter(Boolean)]));
  const priorities = tasks.filter((task) => task.rating.score >= 70).length;
  const matchCount = profile ? tasks.filter((task) => task.rating.score >= 40 && (task.requiredSkills.length > 0 ? task.requiredSkills.every((skill) => profile.skills.some((own) => own.toLowerCase() === skill.toLowerCase())) : profile.interests.some((interest) => [task.topic, task.industry ?? ""].some((value) => value.toLowerCase() === interest.toLowerCase())))).length : 0;
  const viewTitle = view === "mine" ? "Мои задачи" : view === "saved" ? "Мои квесты" : "Каталог задач";
  const subtitle = view === "mine" ? "Дайте своей задаче понятное начало." : view === "saved" ? "Задачи, к которым хочется вернуться." : "Реальные задачи бизнеса. Пространство для вашего опыта.";

  return <SidebarProvider style={{ "--sidebar-width": "242px", "--sidebar-width-mobile": "260px" } as React.CSSProperties}>
    <Sidebar className="alem-sidebar">
      <SidebarHeader className="brand-area"><button onClick={() => navigate("catalog")} className="brand" aria-label="Alem — главная"><span className="brand-symbol">a</span><span>alem<span className="brand-dot">.</span></span></button><span className="brand-caption">Бизнес встречает талант</span></SidebarHeader>
      <SidebarContent className="sidebar-body"><p className="nav-caption">РАБОЧЕЕ ПРОСТРАНСТВО</p><SidebarMenu>
        <SidebarMenuItem><WorkspaceNavButton isActive={view === "catalog" && !editor} onClick={() => navigate("catalog")}><LayoutGrid/><span>Каталог задач</span><span className="nav-pill">{view === "catalog" ? tasks.length : ""}</span></WorkspaceNavButton></SidebarMenuItem>
        <SidebarMenuItem><WorkspaceNavButton isActive={(view === "mine" || view === "saved") && !editor} onClick={() => navigate(role === "business" ? "mine" : "saved")}>{role === "business" ? <BriefcaseBusiness/> : <Bookmark/>}<span>{role === "business" ? "Мои задачи" : "Мои квесты"}</span></WorkspaceNavButton></SidebarMenuItem>
        {role === "student" && <SidebarMenuItem><WorkspaceNavButton onClick={() => { setSkillDraft(profile?.skills ?? []); setProfileOpen(true); }}><GraduationCap/><span>Мои навыки</span></WorkspaceNavButton></SidebarMenuItem>}
      </SidebarMenu><div className="sidebar-note"><div className="sidebar-note-icon"><TrendingUp size={20}/></div><strong>{role === "business" ? "Сильный старт с понятной задачей" : "Найдите свою практику"}</strong><p>{role === "business" ? "Дополняйте задачу, повышайте её готовность и поднимайтесь в каталоге." : "Сравнивайте задачи по готовности и сохраняйте подходящие квесты."}</p><button onClick={() => setHelpOpen(true)}>Как работает рейтинг <ArrowRight size={15}/></button></div></SidebarContent>
      <SidebarFooter className="sidebar-bottom"><button className="help-link" onClick={() => setHelpOpen(true)}><CircleHelp size={18}/> О платформе и рейтинге</button><div className="sidebar-user"><span className="user-avatar">{role === "business" ? "Б" : profile?.name.charAt(0) || "С"}</span><span><strong>{role === "business" ? "Бизнесмен" : profile?.name || "Студент"}</strong><small>Тестовый профиль</small></span><span className="demo-dot" title="Демо-режим"/></div></SidebarFooter>
    </Sidebar>
    <SidebarInset className="workspace"><header className="topbar"><div className="breadcrumb"><SidebarTrigger className="mobile-menu" aria-label="Открыть меню"/><span>Рабочее пространство</span><ChevronRight size={14}/><strong>{editor ? "Конструктор задачи" : viewTitle}</strong></div><div className="role-area"><span className="role-label">Тестовая роль</span><Tabs value={role} onValueChange={changeRole}><TabsList className="role-switch"><TabsTrigger value="business"><BriefcaseBusiness size={15}/>Бизнесмен</TabsTrigger><TabsTrigger value="student"><GraduationCap size={16}/>Студент</TabsTrigger></TabsList></Tabs></div></header>
      <section className="main-content" aria-label="Работа с задачами">{editor ? <TaskEditor task={editor === "new" ? null : editor} onDirtyChange={setEditorDirty} onClose={() => { closeEditor(); setView("mine"); }} onSaved={() => { closeEditor(); setView("mine"); refresh(); }}/> : <>
        <div className="page-heading"><div><div className="eyebrow">{role === "business" ? "ДЛЯ БИЗНЕСА" : "ДЛЯ СТУДЕНТОВ"}</div><h1>{viewTitle}<span className="heading-dot">.</span></h1><p>{subtitle}</p></div>{role === "business" ? <Button className="primary-button" onClick={() => setEditor("new")}><Plus size={18}/>Создать задачу</Button> : <Button variant="outline" className="profile-button" onClick={() => { setSkillDraft(profile?.skills ?? []); setProfileOpen(true); }}><SlidersHorizontal size={17}/>Мои навыки</Button>}</div>
        <section className="overview" aria-label="Обзор задач"><div className="overview-title"><span className="overview-icon"><Compass size={23}/></span><div><strong>{role === "business" ? "От идеи к совместной работе" : "Ваша следующая практика — здесь"}</strong><p>{role === "business" ? "Расскажите о задаче. Студенты найдут, где принести пользу." : "Выбирайте по интересам. Сохраняйте задачи, которые подходят."}</p></div></div><div className="overview-stat"><strong>{loading ? "—" : tasks.length.toString().padStart(2, "0")}</strong><span>{view === "saved" ? "сохранено" : "задач в разделе"}</span></div><div className="overview-stat"><strong>{loading ? "—" : (role === "student" ? matchCount : priorities).toString().padStart(2, "0")}</strong><span>{role === "student" ? "по вашему профилю" : "готовы к старту"}</span></div></section>
        {role === "student" && profile && <div className="skills-strip"><span><Sparkles size={15}/>Ваши навыки</span>{profile.skills.slice(0, 5).map((skill) => <span className="skill-tag" key={skill}>{skill}</span>)}<button onClick={() => { setSkillDraft(profile.skills); setProfileOpen(true); }}>Изменить</button></div>}
        <div className="filters"><div className="search-field"><Search size={18}/><Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Название, компания или навык" aria-label="Поиск задач"/>{search && <button aria-label="Очистить поиск" onClick={() => setSearch("")}><X size={16}/></button>}</div><Select value={topic} onValueChange={setTopic}><SelectTrigger aria-label="Направление" className="filter-select"><SelectValue/></SelectTrigger><SelectContent><SelectItem value="all">Все направления</SelectItem>{availableTopics.map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}</SelectContent></Select><Select value={readiness} onValueChange={setReadiness}><SelectTrigger aria-label="Уровень готовности" className="filter-select readiness-select"><SelectValue/></SelectTrigger><SelectContent><SelectItem value="all">Любая готовность</SelectItem>{Object.entries(LEVELS).map(([key, value]) => <SelectItem key={key} value={key}>{value.label} · {value.range}</SelectItem>)}</SelectContent></Select></div>
        <div className="results-heading"><span>{loading ? "Загружаем задачи…" : `${visible.length} ${plural(visible.length, "задача", "задачи", "задач")}`}</span><span><ArrowDownWideNarrow size={16}/>По рейтингу готовности</span></div>
        {error ? <div className="empty-state" role="alert"><CircleHelp size={34}/><h2>Не удалось загрузить задачи</h2><p>{error}</p><Button onClick={refresh}>Попробовать снова</Button></div> : loading ? <div className="task-grid">{[1, 2, 3, 4].map((n) => <Skeleton className="card-skeleton" key={n}/>)}</div> : visible.length ? <div className="task-grid">{visible.map((task) => <TaskCard key={task.id} task={task} role={role} saved={savedTasks.some((item) => item.id === task.id)} onOpen={() => setDetail(task)} onEdit={() => { api.getTask(task.id, true).then(setEditor).catch((err) => toast.error(err.message)); }}/>)}</div> : <div className="empty-state"><Search size={34}/><h2>{view === "saved" && !search && topic === "all" && readiness === "all" ? "Здесь будут ваши квесты" : "Пока ничего не найдено"}</h2><p>{view === "saved" ? "Сохраните интересную задачу из каталога, чтобы вернуться к ней позже." : "Попробуйте другое название или уберите фильтры."}</p><Button variant="outline" onClick={() => { if (view === "saved") navigate("catalog"); else { setSearch(""); setTopic("all"); setReadiness("all"); } }}>{view === "saved" ? "Открыть каталог" : "Сбросить фильтры"}</Button></div>}
        <div className="catalog-footnote"><ShieldCheck size={16}/><p>Рейтинг показывает готовность описания. Все опубликованные задачи доступны независимо от баллов.</p></div>
      </>}</section>
    </SidebarInset>
    {detail && <TaskDetails task={detail} role={role} saved={savedTasks.some((item) => item.id === detail.id)} onClose={() => setDetail(null)} onEdit={(task) => { setDetail(null); api.getTask(task.id, true).then(setEditor).catch((err) => toast.error(err.message)); }} onSave={saveTask}/>}
    <Dialog open={Boolean(quest) && role === "student" && !editor && !detail && !profileOpen} onOpenChange={(open) => { if (!open && !busy) setQuest(null); }}><DialogContent className="quest-dialog"><DialogHeader><span className="quest-emblem"><Sparkles size={30}/></span><span className="eyebrow">ПЕРСОНАЛЬНАЯ РЕКОМЕНДАЦИЯ</span><DialogTitle>Есть квест для вашего профиля</DialogTitle><DialogDescription>Совпадение по навыкам или интересам. Решение за вами.</DialogDescription></DialogHeader>{quest && <><div className="quest-preview"><span className="topic-label">{quest.task.topic} · {quest.task.company}</span><h3>{quest.task.fields.title}</h3><p>{quest.task.fields.need}</p><div className="quest-skills">{quest.matchedSkills.map((skill) => <span key={skill}><Check size={13}/>{skill}</span>)}{quest.matchedInterests?.map((interest) => <span key={interest}><Check size={13}/>Интерес: {interest}</span>)}</div><div className="quest-score"><Target size={16}/>Готовность задачи <strong>{quest.task.rating.score}/100</strong></div></div><p className="quest-explainer">Сохранение квеста выражает ваш интерес. Команду для работы выбирает бизнес.</p><div className="quest-actions"><Button variant="outline" disabled={busy} onClick={() => decideQuest("dismissed")}>Пропустить</Button><Button disabled={busy} onClick={() => decideQuest("saved")}>{busy ? <LoaderCircle className="spin" size={16}/> : <Bookmark size={16}/>}Сохранить квест</Button></div><button className="text-link centered" onClick={() => { setDetail(quest.task); setQuest(null); }}>Сначала посмотреть задачу <ArrowRight size={15}/></button></>}</DialogContent></Dialog>
    <Dialog open={profileOpen} onOpenChange={(open) => { if (!busy) setProfileOpen(open); }}><DialogContent className="profile-dialog"><DialogHeader><span className="eyebrow">ПРОФИЛЬ СТУДЕНТА</span><DialogTitle>Что вы умеете?</DialogTitle><DialogDescription>Выберите навыки — по ним мы подберём квесты. Весь каталог остаётся доступным.</DialogDescription></DialogHeader><label className="profile-field">Тестовый профиль<Select value={profileId} onValueChange={(id) => { setProfileId(id); setSkillDraft(profiles.find((item) => item.id === id)?.skills || []); setQuest(null); }}><SelectTrigger><SelectValue/></SelectTrigger><SelectContent>{profiles.map((item) => <SelectItem value={item.id} key={item.id}>{item.name} · {item.course}</SelectItem>)}</SelectContent></Select></label><div className="skill-picker">{SKILLS.map((skill) => <button className={skillDraft.includes(skill) ? "selected" : ""} aria-pressed={skillDraft.includes(skill)} key={skill} onClick={() => setSkillDraft((items) => items.includes(skill) ? items.filter((item) => item !== skill) : [...items, skill])}>{skillDraft.includes(skill) ? <Check size={15}/> : <Plus size={15}/>} {skill}</button>)}</div><Button disabled={busy || !profileId} onClick={updateSkills}>{busy && <LoaderCircle className="spin" size={16}/>}Сохранить навыки</Button></DialogContent></Dialog>
    <Dialog open={helpOpen} onOpenChange={setHelpOpen}><DialogContent className="help-dialog"><DialogHeader><span className="eyebrow">ПОНЯТНАЯ ГОТОВНОСТЬ</span><DialogTitle>У каждой задачи свой рейтинг</DialogTitle><DialogDescription>Баллы получают заполненные и подтверждённые бизнесом сведения. Чем понятнее задача, тем выше её место в каталоге.</DialogDescription></DialogHeader><div className="rubric-list">{[["Контекст и потребность",20],["Данные и материалы",20],["Ожидаемый результат",15],["Критерии успеха",15],["Ограничения",10],["Пользователи",10],["Связь с бизнесом",10]].map(([label, weight]) => <div key={label}><span>{label}</span><strong>{weight}</strong></div>)}</div><p className="help-note">Рейтинг оценивает готовность описания, а не известность компании. Он не подтверждает достоверность данных. Даже задачу с низким баллом можно открыть и сохранить.</p><Button onClick={() => setHelpOpen(false)}>Понятно</Button></DialogContent></Dialog>
    <AlertDialog open={Boolean(pendingNavigation)} onOpenChange={(open) => { if (!open) setPendingNavigation(null); }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Оставить несохранённые изменения?</AlertDialogTitle><AlertDialogDescription>Изменения в этой форме ещё не сохранены. Можно вернуться и сохранить черновик.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>Вернуться к задаче</AlertDialogCancel><AlertDialogAction onClick={() => { const action = pendingNavigation; setPendingNavigation(null); action?.(); }}>Выйти без сохранения</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
    <Toaster position="bottom-right" richColors closeButton/>
  </SidebarProvider>;
}
function WorkspaceNavButton(props: React.ComponentProps<typeof SidebarMenuButton>) {
  const { setOpenMobile } = useSidebar();
  return <SidebarMenuButton {...props} onClick={(event) => { props.onClick?.(event); setOpenMobile(false); }}/>;
}
function TaskCard({ task, role, saved, onOpen, onEdit }: { task: Task; role: Role; saved: boolean; onOpen: () => void; onEdit: () => void }) {
  return <article className={`task-card ${task.rating.level === "priority" ? "priority-card" : ""}`}><div className="card-top"><span className={`company-mark topic-${TOPICS.indexOf(task.topic)}`}>{TOPIC_MARKS[task.topic] || task.company.charAt(0)}</span><div className="company-info"><strong>{task.company}</strong><span>{task.topic}</span></div><span className={`readiness-badge level-${task.rating.level}`}>{!task.published ? "Черновик" : LEVELS[task.rating.level].label}</span></div><button className="task-title" onClick={onOpen}><h2>{task.fields.title || "Без названия"}</h2></button><p className="task-description">{task.fields.need || task.fields.context || "Добавьте описание потребности, чтобы студентам было проще понять задачу."}</p><div className="card-skills">{task.requiredSkills.length ? task.requiredSkills.slice(0, 4).map((skill) => <span key={skill}>{skill}</span>) : <span>Навыки уточняются</span>}</div><div className="card-rating"><div><span>Готовность задачи</span><strong>{task.rating.score}<small> / 100</small></strong></div><Progress value={task.rating.score} aria-label={`Готовность ${task.rating.score} из 100`}/></div><div className="card-bottom"><span>{task.hasUnpublishedChanges ? "Есть неопубликованные правки" : task.published ? "Открыта для студентов" : "Пока видна только вам"}</span><button aria-label={`${role === "business" && !task.published ? "Дополнить" : "Подробнее"}: ${task.fields.title}`} onClick={role === "business" && !task.published ? onEdit : onOpen}>{saved ? <Bookmark size={15} fill="currentColor"/> : null}{role === "business" && !task.published ? "Дополнить" : "Подробнее"}<ArrowRight size={16}/></button></div></article>;
}
function plural(n: number, one: string, few: string, many: string) { const a = n % 100; return a >= 11 && a <= 14 ? many : n % 10 === 1 ? one : n % 10 >= 2 && n % 10 <= 4 ? few : many; }
