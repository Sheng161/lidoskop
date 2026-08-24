"use client";

import { useQuery } from "@tanstack/react-query";
import { Play, Sparkles } from "lucide-react";
import { FormEvent, useState } from "react";
import { api, Job } from "@/lib/api";
import { Badge, ErrorBox, PageHeader } from "@/components/ui";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [city, setCity] = useState("");
  const [region, setRegion] = useState("");
  const [roles, setRoles] = useState("Директор по маркетингу");
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const job = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api<Job>(`/jobs/${jobId}`),
    enabled: Boolean(jobId),
    refetchInterval: (state) => ["queued", "running"].includes(state.state.data?.status ?? "") ? 1200 : false,
  });

  async function plan(event: FormEvent) {
    event.preventDefault(); setError(""); setBusy(true);
    try {
      const result = await api<Job>("/search/plan", { method: "POST", body: JSON.stringify({ query, city: city || null, region: region || null, target_roles: roles.split(",").map(v => v.trim()).filter(Boolean) }) });
      setJobId(result.id);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Не удалось построить план"); }
    finally { setBusy(false); }
  }

  async function start() {
    if (!jobId) return; setBusy(true); setError("");
    try { await api(`/jobs/${jobId}/start`, { method: "POST" }); await job.refetch(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Не удалось запустить"); }
    finally { setBusy(false); }
  }

  return <>
    <PageHeader eyebrow="Исследование" title="Найдите компании, которым вы полезны" description="Опишите сегмент на естественном языке. Лидоскоп сначала покажет план, а затем соберёт только подтверждённые данные из подключённых источников." />
    <div className="grid">
      <form className="card span-8 stack" onSubmit={plan}>
        <div className="field"><label htmlFor="query">Кого ищем</label><textarea id="query" required minLength={8} value={query} onChange={e => setQuery(e.target.value)} placeholder="Например: Найди производителей мебели в Казани с активным сайтом и директором по маркетингу" /></div>
        <div className="form-grid"><div className="field"><label htmlFor="city">Город</label><input id="city" value={city} onChange={e => setCity(e.target.value)} placeholder="Казань" /></div><div className="field"><label htmlFor="region">Регион</label><input id="region" value={region} onChange={e => setRegion(e.target.value)} placeholder="Республика Татарстан" /></div></div>
        <div className="field"><label htmlFor="roles">Целевые роли ЛПР, через запятую</label><input id="roles" value={roles} onChange={e => setRoles(e.target.value)} /></div>
        {error && <ErrorBox message={error} />}
        <div className="row between"><span className="hint">До запуска вы увидите источники и действия. GigaChat не используется как источник фактов.</span><button className="button" disabled={busy}><Sparkles size={17} />{busy ? "Готовим…" : "Построить план"}</button></div>
      </form>
      <aside className="card span-4"><h3>Принципы поиска</h3><div className="stack hint"><div>01 · Организации поступают из реального подключённого API.</div><div>02 · Сайт проверяется с учётом robots.txt и SSRF-защиты.</div><div>03 · Каждый ЛПР, контакт и вывод связан с доказательством.</div><div>04 · «Не найдено» не считается подтверждённым отсутствием.</div></div></aside>
    </div>
    {jobId && <section className="card" style={{marginTop:18}}><div className="row between"><div><div className="eyebrow">План исследования</div><h2 style={{marginBottom:4}}>Проверка запроса</h2></div>{job.data && <Badge value={job.data.status} />}</div>
      {job.isLoading && <div className="loading">GigaChat формирует структурированный план…</div>}
      {job.data?.error && <ErrorBox message={job.data.error} />}
      {job.data?.plan && <><div className="code">{JSON.stringify(job.data.plan, null, 2)}</div><div className="row between" style={{marginTop:16}}><span className="hint">Запуск создаст фоновую задачу. Прогресс появится в разделе «Задачи».</span><button className="button" onClick={start} disabled={busy || job.data.status !== "draft"}><Play size={17} />Запустить исследование</button></div></>}
      {job.data && ["queued","running"].includes(job.data.status) && <div style={{marginTop:16}}><div className="progress"><span style={{width:`${job.data.progress}%`}} /></div><p className="hint">Этап: {job.data.stage}</p></div>}
    </section>}
  </>;
}
