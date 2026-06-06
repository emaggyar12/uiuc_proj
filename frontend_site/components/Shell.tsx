"use client";

import type React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { BarChart3, ListFilter, Repeat2, Target, Users } from "lucide-react";

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
    <div className="min-h-screen bg-[#f3f6f1]">
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
                  active ? "bg-white text-ink" : "text-slate-200 hover:bg-white/10 hover:text-white",
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>

      <div className="lg:pl-60">
        <header className="sticky top-0 z-10 border-b border-line bg-panel/95 px-4 py-3 backdrop-blur lg:hidden">
          <div className="mb-3 text-lg font-semibold text-ink">Roster Lab</div>
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
                    active ? "border-ink bg-ink text-white" : "border-line bg-white text-slate-700",
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
