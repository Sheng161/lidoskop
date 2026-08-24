import type { Metadata } from "next";
import { Providers } from "@/components/providers";
import { Sidebar } from "@/components/sidebar";
import "./globals.css";

export const metadata: Metadata = { title: "Лидоскоп", description: "Доказательный поиск российских B2B-компаний и ЛПР" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ru"><body><Providers><Sidebar /><main className="main">{children}</main></Providers></body></html>;
}
