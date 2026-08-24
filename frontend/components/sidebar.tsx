"use client";

import {
  Activity,
  BriefcaseBusiness,
  Building2,
  FileDown,
  GitFork,
  Menu,
  Radar,
  Search,
  Settings,
  SlidersHorizontal,
  Users,
  X,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const links = [
  ["/", "Поиск", Search],
  ["/jobs", "Задачи", Activity],
  ["/companies", "Компании", Building2],
  ["/people", "ЛПР", Users],
  ["/graph", "Граф ресурсов", GitFork],
  ["/reports", "Отчёты", FileDown],
  ["/sources", "Источники", SlidersHorizontal],
  ["/services", "Мои услуги", BriefcaseBusiness],
  ["/opportunities", "Возможности", Zap],
  ["/settings", "Настройки", Settings],
  ["/diagnostics", "Диагностика", Radar],
] as const;

export function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="mobile-menu" onClick={() => setOpen(true)} aria-label="Открыть меню"><Menu /></button>
      {open && <button className="scrim" onClick={() => setOpen(false)} aria-label="Закрыть меню" />}
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand"><div className="brand-mark"><Radar size={22} /></div><div><b>Лидоскоп</b><span>Доказательный поиск</span></div></div>
        <button className="close-menu" onClick={() => setOpen(false)} aria-label="Закрыть"><X /></button>
        <nav>
          {links.map(([href, label, Icon]) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return <Link key={href} href={href} className={active ? "active" : ""} onClick={() => setOpen(false)}><Icon size={18} /><span>{label}</span></Link>;
          })}
        </nav>
        <div className="sidebar-note"><span className="status-dot" />Локальный режим</div>
      </aside>
    </>
  );
}

