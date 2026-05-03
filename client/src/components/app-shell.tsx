"use client";

import { Activity, FileText, Files, LogOut, MessageSquare, Plus, Search } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth-store";

const nav: Array<{ href: Route; label: string; icon: typeof Search }> = [
  { href: "/dashboard", label: "Overview", icon: Search },
  { href: "/ingest", label: "Ingest", icon: Plus },
  { href: "/documents", label: "Library", icon: Files },
  { href: "/notes", label: "Notes", icon: FileText },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/debug", label: "Debug", icon: Activity },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { accessToken, clearSession } = useAuthStore();
  const isPublicRoute = pathname === "/" || pathname.startsWith("/auth");

  useEffect(() => {
    if (!accessToken && !isPublicRoute) {
      router.replace("/auth");
    }
  }, [accessToken, isPublicRoute, router]);

  if (isPublicRoute) {
    return <>{children}</>;
  }

  return (
    <div className="min-h-screen bg-black text-white">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-neutral-900 bg-black md:block">
        <Link href="/dashboard" className="flex h-20 items-center gap-3 border-b border-neutral-900 px-5">
          <span className="text-2xl font-normal tracking-tight text-white">CORTEX</span>
          <span className="font-jetbrains rounded-md border border-white/10 bg-white/[0.03] px-2 py-1 text-xs font-light text-neutral-500">
            v0.1.0
          </span>
        </Link>
        <nav className="space-y-1 px-4 py-6">
          {nav.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex h-9 items-center gap-2 rounded-md px-2 text-sm font-light text-neutral-500 transition-colors hover:bg-white/10 hover:text-white",
                  active && "bg-white/[0.08] text-white hover:bg-white/[0.12] hover:text-white",
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="absolute bottom-4 left-4 right-4">
          <Button
            variant="ghost"
            className="w-full justify-start font-light"
            onClick={() => {
              clearSession();
              router.replace("/auth");
            }}
          >
            <LogOut className="h-4 w-4" />
            Logout
          </Button>
        </div>
      </aside>
      <header className="sticky top-0 z-10 border-b border-neutral-900 bg-black/95 backdrop-blur md:hidden">
        <div className="flex h-14 items-center justify-between px-4">
          <Link href="/dashboard" className="flex items-center gap-2">
            <span className="text-lg font-normal tracking-tight text-white">CORTEX</span>
            <span className="font-jetbrains rounded-md border border-white/10 bg-white/[0.03] px-2 py-1 text-[10px] font-light text-neutral-500">
              v0.1.0
            </span>
          </Link>
          <Button variant="ghost" size="sm" onClick={clearSession} className="font-light">
            Logout
          </Button>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2">
          {nav.map((item) => (
            <Link key={item.href} href={item.href} className="rounded-md px-2 py-1 text-xs text-neutral-500">
              {item.label}
            </Link>
          ))}
        </nav>
      </header>
      <main className="md:pl-64">{children}</main>
    </div>
  );
}
