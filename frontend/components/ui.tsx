import { AlertCircle, Inbox, LoaderCircle } from "lucide-react";

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description: string; actions?: React.ReactNode }) {
  return <header className="page-header"><div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}<h1>{title}</h1><p>{description}</p></div>{actions && <div className="header-actions">{actions}</div>}</header>;
}

export function EmptyState({ title, text, action }: { title: string; text: string; action?: React.ReactNode }) {
  return <div className="empty"><div className="empty-icon"><Inbox /></div><h3>{title}</h3><p>{text}</p>{action}</div>;
}

export function Loading() { return <div className="loading"><LoaderCircle className="spin" /> Загрузка…</div>; }
export function ErrorBox({ message }: { message: string }) { return <div className="alert error"><AlertCircle size={18} />{message}</div>; }

const labels: Record<string, string> = { draft: "План готов", queued: "В очереди", running: "Выполняется", partial: "Частичный результат", completed: "Завершено", failed: "Ошибка", cancelled: "Отменено", connected: "Подключён", configured: "Настроен", not_connected: "Не подключён", confirmed: "Подтверждён", probable: "Вероятный", unverified: "Не проверен", outdated: "Устарел", active: "Активна", accepted: "Принято", rejected: "Отклонено", edited: "Изменено", pending: "На рассмотрении" };
export function Badge({ value }: { value: string }) { return <span className={`badge badge-${value}`}>{labels[value] ?? value}</span>; }

export function Score({ value }: { value: number | null }) {
  if (value === null) return <span className="muted">Не рассчитана</span>;
  return <span className={`score ${value >= 70 ? "good" : value >= 40 ? "medium" : "low"}`}>{Math.round(value)}</span>;
}

