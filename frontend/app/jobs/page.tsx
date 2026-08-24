"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { api, Job } from "@/lib/api";
import { Badge, EmptyState, ErrorBox, Loading, PageHeader } from "@/components/ui";

export default function JobsPage() {
  const client = useQueryClient();
  const query = useQuery({ queryKey:["jobs"], queryFn:()=>api<Job[]>("/jobs"), refetchInterval:2500 });
  async function cancel(id:string){ await api(`/jobs/${id}/cancel`,{method:"POST"}); await client.invalidateQueries({queryKey:["jobs"]}); }
  return <><PageHeader eyebrow="Очередь" title="Задачи исследования" description="Реальный прогресс фоновых этапов, частичные результаты и ошибки источников." />
    {query.isLoading ? <Loading /> : query.error ? <ErrorBox message={query.error.message} /> : !query.data?.length ? <EmptyState title="Задач пока нет" text="Сначала сформируйте план поиска и запустите исследование." action={<Link className="button" href="/">Начать поиск</Link>} /> : <div className="table-wrap"><table className="table"><thead><tr><th>Запрос</th><th>Город</th><th>Статус</th><th>Прогресс</th><th>Создана</th><th /></tr></thead><tbody>{query.data.map(job=><tr key={job.id}><td><div className="name">{job.query}</div><div className="muted">{job.stage}{job.error ? ` · ${job.error}` : ""}</div></td><td>{job.city ?? "—"}</td><td><Badge value={job.status} /></td><td style={{minWidth:140}}><div className="progress"><span style={{width:`${job.progress}%`}} /></div><div className="muted">{job.progress}%</div></td><td>{new Date(job.created_at).toLocaleString("ru-RU")}</td><td><div className="row">{["running","queued"].includes(job.status) && <button className="button danger" onClick={()=>cancel(job.id)}>Отменить</button>}<Link className="button ghost" href={`/companies?job_id=${job.id}`}>Результаты</Link></div></td></tr>)}</tbody></table></div>}
  </>;
}

