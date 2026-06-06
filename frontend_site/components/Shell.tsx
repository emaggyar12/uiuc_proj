"use client";

import type React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { BarChart3, ListFilter, Repeat2, Target, Users } from "lucide-react";
import { ThemeToggle } from "@/components/ThemeToggle";

const navItems = [
  { href: "/", label: "Players", icon: BarChart3 },
  { href: "/portal", label: "Portal", icon: ListFilter },
  { href: "/simulator", label: "Simulator", icon: Repeat2 },
  { href: "/recommendations", label: "Recommendations", icon: Target },
  { href: "/teams/uconn", label: "Teams", icon: Users },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-page">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-60 border-r border-line bg-[#17202a] text-white lg:block">
        <div className="border-b border-white/10 px-5 py-5">
          <div className="text-lg font-semibold">Roster Lab</div>
          <div className="mt-1 text-xs text-slate-300">Transfer portal operations</div>
        </div>
        <nav className="space-y-1 px-3 py-4">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={clsx(
                  "flex h-10 items-center gap-3 rounded px-3 text-sm font-medium transition",
                  active
                    ? "bg-[#f8faf7] text-[#17202a] dark:bg-slate-700 dark:text-white"
                    : "text-slate-200 hover:bg-white/10 hover:text-white",
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="absolute bottom-0 left-0 right-0 border-t border-white/10 p-3">
          <ThemeToggle />
        </div>
      </aside>

      <div className="lg:pl-60">
        <header className="sticky top-0 z-10 border-b border-line bg-panel/95 px-4 py-3 backdrop-blur lg:hidden">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="text-lg font-semibold text-ink">Roster Lab</div>
            <div className="rounded bg-[#17202a] p-1">
              <ThemeToggle />
            </div>
          </div>
          <nav className="flex gap-2 overflow-x-auto">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={clsx(
                    "flex h-9 shrink-0 items-center gap-2 rounded border px-3 text-sm font-medium",
                    active
                      ? "border-emerald-600 bg-emerald-600 text-white dark:border-emerald-400 dark:bg-emerald-500 dark:text-slate-950"
                      : "border-line bg-white text-slate-700",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 md:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
