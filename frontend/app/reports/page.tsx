import { Download } from "lucide-react";
import { API_URL } from "@/lib/api";
import { PageHeader } from "@/components/ui";
export default function ReportsPage(){return <><PageHeader eyebrow="Экспорт" title="Отчёты" description="Экспортируйте только реально собранные компании. В пустой базе файлы содержат только заголовки."/><div className="grid"><div className="card span-4"><h3>CSV</h3><p className="muted">Для CRM и быстрой обработки.</p><a className="button" href={`${API_URL}/exports/csv`}><Download size={16}/>Скачать</a></div><div className="card span-4"><h3>XLSX</h3><p className="muted">Рабочая книга для Excel.</p><a className="button" href={`${API_URL}/exports/xlsx`}><Download size={16}/>Скачать</a></div><div className="card span-4"><h3>JSON</h3><p className="muted">Машиночитаемый экспорт.</p><a className="button" href={`${API_URL}/exports/json`}><Download size={16}/>Скачать</a></div></div></>}

