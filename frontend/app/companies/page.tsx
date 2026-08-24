"use client";

import { useQuery } from "@tanstack/react-query";
import { Download, Search } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, API_URL, CompanyRow } from "@/lib/api";
import { EmptyState, ErrorBox, Loading, PageHeader, Score } from "@/components/ui";

function Companies() {
  const params=useSearchParams(); const jobId=params.get("job_id"); const [search,setSearch]=useState("");
  const query=useQuery({queryKey:["companies",search,jobId],queryFn:()=>api<CompanyRow[]>(`/companies?q=${encodeURIComponent(search)}${jobId?`&job_id=${jobId}`:""}`)});
  return <><PageHeader eyebrow="База" title="Компании" description="Только организации, полученные реальным исследованием. Откройте карточку, чтобы увидеть доказательства." actions={<div className="row"><a className="button secondary" href={`${API_URL}/exports/csv${jobId?`?job_id=${jobId}`:""}`}><Download size={16}/>CSV</a><a className="button secondary" href={`${API_URL}/exports/xlsx${jobId?`?job_id=${jobId}`:""}`}><Download size={16}/>XLSX</a></div>} />
  <div className="card" style={{marginBottom:18}}><div className="field"><label htmlFor="company-search">Поиск по названию или ИНН</label><div className="row"><Search size={18}/><input id="company-search" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Введите название или ИНН"/></div></div></div>
  {query.isLoading?<Loading/>:query.error?<ErrorBox message={query.error.message}/>:!query.data?.length?<EmptyState title="Компаний пока нет" text="Результаты появятся после выполнения исследования через подключённые источники." action={<Link className="button" href="/">Создать поиск</Link>}/>:<div className="table-wrap"><table className="table"><thead><tr><th>Компания</th><th>ИНН / ОГРН</th><th>Город</th><th>Сайт</th><th>Оценка</th></tr></thead><tbody>{query.data.map(row=><tr key={row.id}><td><Link className="name resource-link" href={`/companies/${row.id}`}>{row.name}</Link><div className="muted">{row.status??"Статус не указан"}</div></td><td>{row.inn??"—"}<div className="muted">{row.ogrn??""}</div></td><td>{row.city??"—"}</td><td>{row.website?<a className="resource-link" href={row.website} target="_blank" rel="noreferrer">Открыть</a>:<span className="muted">Не обнаружен</span>}</td><td><Score value={row.score}/></td></tr>)}</tbody></table></div>}</>;
}
export default function CompaniesPage(){return <Suspense fallback={<Loading/>}><Companies/></Suspense>}

