"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  {
    href: "/dashboard",
    label: "Overview",
    icon: (
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <rect x="1" y="1" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.4" />
        <rect x="8" y="1" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.4" />
        <rect x="1" y="8" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.4" />
        <rect x="8" y="8" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.4" />
      </svg>
    ),
  },
  {
    href: "/dashboard/commits",
    label: "Commits",
    icon: (
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <circle cx="7" cy="7" r="2.5" stroke="currentColor" strokeWidth="1.4" />
        <line x1="7" y1="1" x2="7" y2="4.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        <line x1="7" y1="9.5" x2="7" y2="13" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    href: "/dashboard/branches",
    label: "Branches",
    icon: (
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <circle cx="3.5" cy="3.5" r="1.5" stroke="currentColor" strokeWidth="1.4" />
        <circle cx="3.5" cy="10.5" r="1.5" stroke="currentColor" strokeWidth="1.4" />
        <circle cx="10.5" cy="7" r="1.5" stroke="currentColor" strokeWidth="1.4" />
        <line x1="3.5" y1="5" x2="3.5" y2="9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        <path d="M3.5 5 C 3.5 7 6.5 7 9 7" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    href: "/dashboard/diff",
    label: "Diff",
    icon: (
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <rect x="1" y="1" width="12" height="12" rx="2" stroke="currentColor" strokeWidth="1.4" />
        <line x1="4" y1="5" x2="10" y2="5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        <line x1="4" y1="7" x2="8" y2="7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        <line x1="4" y1="9" x2="6" y2="9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    href: "/dashboard/audit",
    label: "Audit Log",
    icon: (
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <rect x="2" y="1" width="10" height="12" rx="1.5" stroke="currentColor" strokeWidth="1.4" />
        <line x1="4.5" y1="4.5" x2="9.5" y2="4.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        <line x1="4.5" y1="7" x2="9.5" y2="7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        <line x1="4.5" y1="9.5" x2="7.5" y2="9.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    href: "/dashboard/replay",
    label: "Replay",
    icon: (
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.4" />
        <path d="M5.5 4.5L10 7L5.5 9.5V4.5Z" fill="currentColor" />
      </svg>
    ),
  },
];

const agents = [
  { name: "compliance-reviewer", online: true },
  { name: "portfolio-optimizer", online: true },
  { name: "risk-assessor", online: true },
  { name: "kyc-verifier", online: false },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <div
      className="flex flex-col min-h-screen"
      style={{ backgroundColor: "#0C0D10" }}
    >
      {/* Top Bar */}
      <header
        className="flex items-center justify-between py-3 px-6 shrink-0"
        style={{ borderBottom: "1px solid #FFFFFF0F" }}
      >
        {/* Left */}
        <div className="flex items-center gap-4">
          {/* Logo */}
          <div className="flex items-center gap-2">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <circle cx="10" cy="10" r="8.5" stroke="#ECECEE" strokeWidth="1.8" />
              <line x1="10" y1="4" x2="10" y2="16" stroke="#ECECEE" strokeWidth="1.8" strokeLinecap="round" />
              <circle cx="7" cy="8" r="1.5" fill="#ECECEE" />
              <circle cx="13" cy="12" r="1.5" fill="#ECECEE" />
            </svg>
            <span
              className="text-[15px] font-semibold tracking-[-0.01em]"
              style={{
                color: "#ECECEE",
                fontFamily: "var(--font-display, 'Space Grotesk', sans-serif)",
              }}
            >
              agit
            </span>
          </div>

          {/* Divider */}
          <div
            className="shrink-0"
            style={{
              width: "1px",
              height: "18px",
              backgroundColor: "#FFFFFF14",
            }}
          />

          {/* Org */}
          <span
            className="text-[13px]"
            style={{
              color: "#8A8A92",
              fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
            }}
          >
            acme-financial
          </span>

          {/* Branch Selector */}
          <button
            className="flex items-center gap-1.5 py-1 px-2.5 rounded-[5px]"
            style={{
              backgroundColor: "#FFFFFF0A",
              border: "1px solid #FFFFFF0F",
            }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full shrink-0"
              style={{ backgroundColor: "#4ADE80" }}
            />
            <span
              className="text-[12px]"
              style={{
                color: "#A0A0AA",
                fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
              }}
            >
              main
            </span>
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
              <path d="M2.5 4L5 6.5L7.5 4" stroke="#6E6E76" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>

        {/* Right */}
        <div className="flex items-center gap-4">
          {/* Status */}
          <div className="flex items-center gap-1.5">
            <span
              className="w-1.5 h-1.5 rounded-full shrink-0"
              style={{ backgroundColor: "#4ADE80" }}
            />
            <span
              className="text-[12px]"
              style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}
            >
              3 agents online
            </span>
          </div>

          {/* Search */}
          <button
            className="flex items-center gap-2 py-1 px-2.5 rounded-[5px]"
            style={{ backgroundColor: "#FFFFFF0A" }}
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <circle cx="5" cy="5" r="3.5" stroke="#4E5060" strokeWidth="1.2" />
              <line x1="7.8" y1="7.8" x2="10.5" y2="10.5" stroke="#4E5060" strokeWidth="1.2" strokeLinecap="round" />
            </svg>
            <span
              className="text-[12px]"
              style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif" }}
            >
              Search
            </span>
            <kbd
              className="text-[10px] px-1 rounded-[3px]"
              style={{
                color: "#4E5060",
                backgroundColor: "#FFFFFF0F",
                border: "1px solid #FFFFFF14",
                fontFamily: "'Inter', sans-serif",
              }}
            >
              ⌘K
            </kbd>
          </button>
        </div>
      </header>

      {/* Body */}
      <div className="flex flex-1 min-h-0">
        {/* Sidebar */}
        <aside
          className="flex flex-col shrink-0 py-4 px-3"
          style={{
            width: "220px",
            borderRight: "1px solid #FFFFFF0F",
          }}
        >
          {/* Nav */}
          <nav className="flex flex-col gap-0.5">
            {navItems.map((item) => {
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className="flex items-center gap-2 py-2 px-2.5 rounded-md"
                  style={{
                    backgroundColor: isActive ? "#FFFFFF0A" : "transparent",
                    color: isActive ? "#ECECEE" : "#6E6E76",
                    fontFamily: "'Inter', sans-serif",
                    fontSize: "13px",
                    fontWeight: isActive ? 500 : 400,
                    textDecoration: "none",
                  }}
                >
                  <span style={{ color: isActive ? "#ECECEE" : "#6E6E76" }}>
                    {item.icon}
                  </span>
                  {item.label}
                </Link>
              );
            })}
          </nav>

          {/* Divider */}
          <div
            className="my-2 shrink-0"
            style={{
              height: "1px",
              backgroundColor: "#FFFFFF0A",
            }}
          />

          {/* Agents Section */}
          <div className="flex flex-col gap-0.5">
            <span
              className="py-1 px-2.5 uppercase"
              style={{
                fontFamily: "'Inter', sans-serif",
                fontSize: "11px",
                fontWeight: 500,
                color: "#4E5060",
                letterSpacing: "0.06em",
              }}
            >
              Agents
            </span>
            {agents.map((agent) => (
              <div
                key={agent.name}
                className="flex items-center gap-2 py-1.5 px-2.5"
              >
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{
                    backgroundColor: agent.online ? "#4ADE80" : "#6E6E76",
                  }}
                />
                <span
                  className="text-[12px] truncate"
                  style={{
                    color: agent.online ? "#A0A0AA" : "#4E5060",
                    fontFamily: "'Inter', sans-serif",
                  }}
                >
                  {agent.name}
                </span>
              </div>
            ))}
          </div>
        </aside>

        {/* Main Content */}
        <main className="flex-1 py-6 px-7 min-w-0">
          {children}
        </main>
      </div>
    </div>
  );
}
