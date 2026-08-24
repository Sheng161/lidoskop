import Link from "next/link";
import { PageHeader, EmptyState } from "@/components/ui";
export default function GraphPage(){return <><PageHeader eyebrow="Связи" title="Граф ресурсов" description="Карта компаний, сайтов, страниц и ЛПР строится по реальным результатам исследования."/><EmptyState title="Выберите компанию" text="Граф доступен из карточки исследованной компании. Пустые или предполагаемые связи не добавляются." action={<Link className="button" href="/companies">Перейти к компаниям</Link>}/></>}
