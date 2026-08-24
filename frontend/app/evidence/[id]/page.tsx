"use client";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { ErrorBox, Loading, PageHeader } from "@/components/ui";
type Evidence={id:string;source_type:string;source_url:string;page_title:string|null;excerpt:string;extraction_method:string;content_hash:string;observed_at:string;confidence:number};
export default function EvidencePage(){const {id}=useParams<{id:string}>();const q=useQuery({queryKey:["evidence",id],queryFn:()=>api<Evidence>(`/evidence/${id}`)});if(q.isLoading)return <Loading/>;if(q.error)return <ErrorBox message={q.error.message}/>;if(!q.data)return null;const e=q.data;return <><PageHeader eyebrow="Происхождение данных" title={e.page_title||"Доказательство"} description={`${e.source_type} · ${new Date(e.observed_at).toLocaleString("ru-RU")} · уверенность ${e.confidence}%`}/><div className="card stack"><a className="resource-link" href={e.source_url} target="_blank" rel="noreferrer">{e.source_url}</a><div><div className="muted">Допустимый фрагмент</div><blockquote>{e.excerpt}</blockquote></div><div className="code">Метод: {e.extraction_method}\nSHA-256: {e.content_hash}</div></div></>}
