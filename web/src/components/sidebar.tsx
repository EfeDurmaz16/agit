"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Dashboard", icon: DashboardIcon },
  { href: "/commits", label: "Commits", icon: CommitsIcon },
  { href: "/branches", label: "Branches", icon: BranchIcon },
  { href: "/audit", label: "Audit Log", icon: AuditIcon },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-60 bg-white border-r border-stone-200 flex flex-col z-40">
      {/* Logo */}
      <div className="px-6 py-5 border-b border-stone-100">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-emerald-600 flex items-center justify-center">
            <span className="text-white text-xs font-bold font-mono">ag</span>
          </div>
          <div>
            <span className="text-base font-semibold tracking-tight text-stone-900">
              agit
            </span>
            <span className="ml-1.5 text-[10px] font-mono text-stone-400 tracking-wide">
              v2.0
            </span>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        <p className="px-3 mb-2 text-[11px] font-medium text-stone-400 uppercase tracking-wider">
          Overview
        </p>
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors",
                isActive
                  ? "bg-emerald-50 text-emerald-700 font-medium"
                  : "text-stone-500 hover:text-stone-900 hover:bg-stone-50"
              )}
            >
              <item.icon active={isActive} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Bottom */}
      <div className="px-4 py-4 border-t border-stone-100">
        <div className="flex items-center gap-2.5 px-2">
          <div className="w-7 h-7 rounded-full bg-stone-100 flex items-center justify-center">
            <span className="text-xs text-stone-500 font-medium">A</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-stone-700 truncate">
              Agent Dashboard
            </p>
            <p className="text-[10px] text-stone-400 font-mono">localhost:8000</p>
          </div>
        </div>
      </div>
    </aside>
  );
}

function DashboardIcon({ active }: { active: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      className={active ? "text-emerald-600" : "text-stone-400"}
    >
      <rect x="1" y="1" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
      <rect x="9" y="1" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
      <rect x="1" y="9" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
      <rect x="9" y="9" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function CommitsIcon({ active }: { active: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      className={active ? "text-emerald-600" : "text-stone-400"}
    >
      <circle cx="8" cy="8" r="3" stroke="currentColor" strokeWidth="1.5" />
      <line x1="8" y1="1" x2="8" y2="5" stroke="currentColor" strokeWidth="1.5" />
      <line x1="8" y1="11" x2="8" y2="15" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function BranchIcon({ active }: { active: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      className={active ? "text-emerald-600" : "text-stone-400"}
    >
      <circle cx="4" cy="4" r="2" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="4" cy="12" r="2" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="12" cy="8" r="2" stroke="currentColor" strokeWidth="1.5" />
      <line x1="4" y1="6" x2="4" y2="10" stroke="currentColor" strokeWidth="1.5" />
      <path d="M4 6 C 4 8 8 8 10 8" stroke="currentColor" strokeWidth="1.5" fill="none" />
    </svg>
  );
}

function AuditIcon({ active }: { active: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      className={active ? "text-emerald-600" : "text-stone-400"}
    >
      <rect x="2" y="1" width="12" height="14" rx="2" stroke="currentColor" strokeWidth="1.5" />
      <line x1="5" y1="5" x2="11" y2="5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <line x1="5" y1="8" x2="11" y2="8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <line x1="5" y1="11" x2="9" y2="11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
