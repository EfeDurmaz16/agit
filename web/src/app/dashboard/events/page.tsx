"use client";

import { useEffect, useRef, useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type EventType = "commit_created" | "branch_created" | "merge_completed" | "revert_performed";

interface StreamEvent {
  id: string;
  type: EventType;
  description: string;
  agent: string;
  timestamp: number; // ms epoch
}

// ---------------------------------------------------------------------------
// Design helpers
// ---------------------------------------------------------------------------
const EVENT_TYPE_COLOR: Record<EventType, string> = {
  commit_created: "#4ADE80",
  branch_created: "#5B8DEF",
  merge_completed: "#E8A44A",
  revert_performed: "#E85D5D",
};

const EVENT_TYPE_LABEL: Record<EventType, string> = {
  commit_created: "commit",
  branch_created: "branch",
  merge_completed: "merge",
  revert_performed: "revert",
};

function relativeTime(ms: number): string {
  const diff = Math.floor((Date.now() - ms) / 1000);
  if (diff < 5) return "just now";
  if (diff < 60) return `${diff}s ago`;
  const mins = Math.floor(diff / 60);
  if (mins < 60) return `${mins}m ago`;
  return `${Math.floor(mins / 60)}h ago`;
}

// ---------------------------------------------------------------------------
// Demo data
// ---------------------------------------------------------------------------
const DEMO_POOL: Omit<StreamEvent, "id" | "timestamp">[] = [
  { type: "commit_created", description: "feat: add portfolio rebalancing logic", agent: "portfolio-optimizer" },
  { type: "branch_created", description: "Created branch feature/kyc-enhancements", agent: "kyc-verifier" },
  { type: "merge_completed", description: "Merged risk-model-v2 into main", agent: "risk-assessor" },
  { type: "commit_created", description: "fix: resolve edge case in compliance check", agent: "compliance-reviewer" },
  { type: "commit_created", description: "chore: update dependency snapshots", agent: "portfolio-optimizer" },
  { type: "revert_performed", description: "Reverted commit a3f92b1 (bad margin calc)", agent: "risk-assessor" },
  { type: "branch_created", description: "Created branch hotfix/audit-timestamp-tz", agent: "compliance-reviewer" },
  { type: "merge_completed", description: "Merged feature/alert-thresholds into staging", agent: "portfolio-optimizer" },
  { type: "commit_created", description: "refactor: simplify KYC document pipeline", agent: "kyc-verifier" },
  { type: "commit_created", description: "test: add regression for empty portfolio case", agent: "risk-assessor" },
  { type: "branch_created", description: "Created branch experiment/llm-signal-filter", agent: "compliance-reviewer" },
  { type: "revert_performed", description: "Reverted branch merge (conflict detected)", agent: "kyc-verifier" },
  { type: "merge_completed", description: "Merged hotfix/session-token into main", agent: "compliance-reviewer" },
  { type: "commit_created", description: "perf: cache regulatory ruleset lookups", agent: "risk-assessor" },
  { type: "commit_created", description: "docs: update agent contract interface spec", agent: "portfolio-optimizer" },
  { type: "branch_created", description: "Created branch feature/multi-currency-support", agent: "risk-assessor" },
  { type: "merge_completed", description: "Merged feature/batch-verification into main", agent: "kyc-verifier" },
  { type: "commit_created", description: "fix: handle null counterparty in swap calc", agent: "compliance-reviewer" },
];

function makeInitialEvents(): StreamEvent[] {
  const now = Date.now();
  return DEMO_POOL.slice(0, 15).map((e, i) => ({
    ...e,
    id: `evt-${(1000 + i).toString(16)}`,
    timestamp: now - (15 - i) * 12_000,
  }));
}

let poolCursor = 15;
function nextDemoEvent(): StreamEvent {
  const template = DEMO_POOL[poolCursor % DEMO_POOL.length];
  poolCursor++;
  return {
    ...template,
    id: `evt-${Date.now().toString(16).slice(-6)}`,
    timestamp: Date.now(),
  };
}

// ---------------------------------------------------------------------------
// Event row
// ---------------------------------------------------------------------------
function EventRow({ event, isNew }: { event: StreamEvent; isNew: boolean }) {
  const color = EVENT_TYPE_COLOR[event.type];
  const label = EVENT_TYPE_LABEL[event.type];

  return (
    <div
      className="flex items-center gap-3 px-4 py-3 transition-all"
      style={{
        borderBottom: "1px solid #FFFFFF06",
        backgroundColor: isNew ? "#5B8DEF08" : "transparent",
      }}
      onMouseEnter={(e) => { if (!isNew) e.currentTarget.style.backgroundColor = "#FFFFFF06"; }}
      onMouseLeave={(e) => { if (!isNew) e.currentTarget.style.backgroundColor = "transparent"; }}
    >
      {/* Colored dot */}
      <span
        className="w-1.5 h-1.5 rounded-full shrink-0"
        style={{ backgroundColor: color, boxShadow: isNew ? `0 0 6px ${color}80` : "none" }}
      />

      {/* Type badge */}
      <span
        className="text-[10px] font-medium px-2 py-0.5 rounded-full shrink-0 uppercase"
        style={{
          backgroundColor: color + "18",
          color,
          fontFamily: "'Inter', sans-serif",
          letterSpacing: "0.04em",
        }}
      >
        {label}
      </span>

      {/* Description */}
      <span
        className="text-[12px] flex-1 truncate"
        style={{ color: "#ECECEE", fontFamily: "'Inter', sans-serif" }}
      >
        {event.description}
      </span>

      {/* Agent */}
      <span
        className="text-[11px] shrink-0 hidden sm:block"
        style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}
      >
        {event.agent}
      </span>

      {/* Timestamp */}
      <span
        className="text-[11px] shrink-0 w-16 text-right"
        style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif" }}
      >
        {relativeTime(event.timestamp)}
      </span>

      {/* Event ID */}
      <span
        className="text-[10px] shrink-0 w-20 text-right"
        style={{
          color: "#4E5060",
          fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
        }}
      >
        {event.id}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------
const ALL_TYPES: EventType[] = [
  "commit_created",
  "branch_created",
  "merge_completed",
  "revert_performed",
];

export default function EventsPage() {
  const [events, setEvents] = useState<StreamEvent[]>(makeInitialEvents);
  const [newId, setNewId] = useState<string | null>(null);
  const [filters, setFilters] = useState<Record<EventType, boolean>>({
    commit_created: true,
    branch_created: true,
    merge_completed: true,
    revert_performed: true,
  });
  const [tick, setTick] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Simulate live incoming events every 3 seconds
  useEffect(() => {
    intervalRef.current = setInterval(() => {
      const next = nextDemoEvent();
      setEvents((prev) => [next, ...prev].slice(0, 100));
      setNewId(next.id);
      setTimeout(() => setNewId(null), 1500);
    }, 3000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  // Tick to update relative timestamps
  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 10_000);
    return () => clearInterval(t);
  }, []);

  // Suppress unused variable warning
  void tick;

  const filtered = events.filter((e) => filters[e.type]);

  // Stats
  const recentWindow = events.filter((e) => Date.now() - e.timestamp < 60_000);
  const eventsPerMin = recentWindow.length;
  const agentCounts = events.reduce<Record<string, number>>((acc, e) => {
    acc[e.agent] = (acc[e.agent] ?? 0) + 1;
    return acc;
  }, {});
  const mostActiveAgent = Object.entries(agentCounts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "—";

  const toggleFilter = (type: EventType) => {
    setFilters((prev) => ({ ...prev, [type]: !prev[type] }));
  };

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <span
            className="text-[18px] font-semibold block"
            style={{
              color: "#ECECEE",
              fontFamily: "var(--font-display, 'Space Grotesk', sans-serif)",
              lineHeight: "22px",
            }}
          >
            Event Stream
          </span>
          <span
            className="text-[12px] mt-1 block"
            style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}
          >
            Live feed of agent-emitted git events
          </span>
        </div>

        {/* Status bar */}
        <div className="flex items-center gap-4">
          {/* Connected */}
          <div className="flex items-center gap-1.5">
            <span
              className="w-1.5 h-1.5 rounded-full shrink-0 animate-pulse"
              style={{ backgroundColor: "#4ADE80", boxShadow: "0 0 6px #4ADE8080" }}
            />
            <span
              className="text-[12px]"
              style={{ color: "#4ADE80", fontFamily: "'Inter', sans-serif" }}
            >
              Connected
            </span>
          </div>

          {/* Divider */}
          <div style={{ width: "1px", height: "16px", backgroundColor: "#FFFFFF14" }} />

          {/* Subscriber count */}
          <div className="flex items-center gap-1.5">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <circle cx="4.5" cy="4" r="2" stroke="#6E6E76" strokeWidth="1.2" />
              <circle cx="8.5" cy="4" r="2" stroke="#6E6E76" strokeWidth="1.2" />
              <path d="M1 10c0-1.7 1.6-3 3.5-3" stroke="#6E6E76" strokeWidth="1.2" strokeLinecap="round" />
              <path d="M11 10c0-1.7-1.6-3-3.5-3S4 8.3 4 10" stroke="#6E6E76" strokeWidth="1.2" strokeLinecap="round" />
            </svg>
            <span
              className="text-[12px]"
              style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}
            >
              4 subscribers
            </span>
          </div>

          {/* Divider */}
          <div style={{ width: "1px", height: "16px", backgroundColor: "#FFFFFF14" }} />

          {/* Total events */}
          <div className="flex items-center gap-1.5">
            <span
              className="text-[12px]"
              style={{ color: "#A0A0AA", fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)" }}
            >
              {events.length}
            </span>
            <span
              className="text-[12px]"
              style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}
            >
              total events
            </span>
          </div>
        </div>
      </div>

      {/* Body: feed + sidebar */}
      <div className="flex gap-3 flex-1 min-h-0">
        {/* Live event feed */}
        <div
          className="flex-1 rounded-[10px] overflow-hidden flex flex-col min-h-0"
          style={{ backgroundColor: "#111318", border: "1px solid #FFFFFF0A" }}
        >
          {/* Feed header */}
          <div
            className="flex items-center justify-between px-4 py-2.5 shrink-0"
            style={{ borderBottom: "1px solid #FFFFFF08", backgroundColor: "#0D0E12" }}
          >
            <div className="flex items-center gap-2">
              <span
                className="w-1.5 h-1.5 rounded-full animate-pulse"
                style={{ backgroundColor: "#4ADE80" }}
              />
              <span
                className="text-[11px] uppercase"
                style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif", letterSpacing: "0.06em" }}
              >
                Live Feed
              </span>
            </div>
            <span
              className="text-[11px]"
              style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif" }}
            >
              {filtered.length} events shown
            </span>
          </div>

          {/* Column labels */}
          <div
            className="flex items-center gap-3 px-4 py-2 shrink-0"
            style={{ borderBottom: "1px solid #FFFFFF06" }}
          >
            <span className="w-1.5 shrink-0" />
            <span
              className="text-[10px] uppercase w-14 shrink-0"
              style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif", letterSpacing: "0.06em" }}
            >
              Type
            </span>
            <span
              className="text-[10px] uppercase flex-1"
              style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif", letterSpacing: "0.06em" }}
            >
              Description
            </span>
            <span
              className="text-[10px] uppercase shrink-0 hidden sm:block"
              style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif", letterSpacing: "0.06em" }}
            >
              Agent
            </span>
            <span
              className="text-[10px] uppercase shrink-0 w-16 text-right"
              style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif", letterSpacing: "0.06em" }}
            >
              Time
            </span>
            <span
              className="text-[10px] uppercase shrink-0 w-20 text-right"
              style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif", letterSpacing: "0.06em" }}
            >
              ID
            </span>
          </div>

          {/* Scrollable rows */}
          <div className="overflow-auto flex-1">
            {filtered.length === 0 ? (
              <div className="flex items-center justify-center h-full">
                <span
                  className="text-[13px]"
                  style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif" }}
                >
                  No events match current filters
                </span>
              </div>
            ) : (
              filtered.map((event) => (
                <EventRow key={event.id} event={event} isNew={event.id === newId} />
              ))
            )}
          </div>
        </div>

        {/* Right sidebar: filters */}
        <div
          className="shrink-0 rounded-[10px] flex flex-col gap-5 p-4"
          style={{
            width: "220px",
            backgroundColor: "#111318",
            border: "1px solid #FFFFFF0A",
          }}
        >
          {/* Filter section */}
          <div>
            <span
              className="text-[10px] uppercase block mb-3"
              style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif", letterSpacing: "0.06em" }}
            >
              Event Types
            </span>
            <div className="flex flex-col gap-2">
              {ALL_TYPES.map((type) => {
                const color = EVENT_TYPE_COLOR[type];
                const label = EVENT_TYPE_LABEL[type];
                const count = events.filter((e) => e.type === type).length;
                return (
                  <label
                    key={type}
                    className="flex items-center gap-2.5 cursor-pointer group"
                  >
                    {/* Custom checkbox */}
                    <div
                      className="w-3.5 h-3.5 rounded-[3px] shrink-0 flex items-center justify-center transition-colors"
                      style={{
                        backgroundColor: filters[type] ? color + "30" : "#FFFFFF08",
                        border: `1px solid ${filters[type] ? color : "#FFFFFF14"}`,
                      }}
                      onClick={() => toggleFilter(type)}
                    >
                      {filters[type] && (
                        <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                          <path d="M1.5 4L3.5 6L6.5 2.5" stroke={color} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      )}
                    </div>

                    <div className="flex items-center gap-1.5 flex-1" onClick={() => toggleFilter(type)}>
                      <span
                        className="w-1.5 h-1.5 rounded-full shrink-0"
                        style={{ backgroundColor: color }}
                      />
                      <span
                        className="text-[12px] flex-1"
                        style={{
                          color: filters[type] ? "#A0A0AA" : "#4E5060",
                          fontFamily: "'Inter', sans-serif",
                        }}
                      >
                        {label}
                      </span>
                      <span
                        className="text-[10px]"
                        style={{
                          color: "#4E5060",
                          fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                        }}
                      >
                        {count}
                      </span>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>

          {/* Divider */}
          <div style={{ height: "1px", backgroundColor: "#FFFFFF0A" }} />

          {/* Select all / none */}
          <div className="flex gap-2">
            <button
              onClick={() => setFilters({ commit_created: true, branch_created: true, merge_completed: true, revert_performed: true })}
              className="flex-1 py-1 rounded-[5px] text-[11px]"
              style={{
                backgroundColor: "#FFFFFF08",
                color: "#A0A0AA",
                fontFamily: "'Inter', sans-serif",
                border: "1px solid #FFFFFF0A",
              }}
            >
              All
            </button>
            <button
              onClick={() => setFilters({ commit_created: false, branch_created: false, merge_completed: false, revert_performed: false })}
              className="flex-1 py-1 rounded-[5px] text-[11px]"
              style={{
                backgroundColor: "#FFFFFF08",
                color: "#6E6E76",
                fontFamily: "'Inter', sans-serif",
                border: "1px solid #FFFFFF0A",
              }}
            >
              None
            </button>
          </div>

          {/* Divider */}
          <div style={{ height: "1px", backgroundColor: "#FFFFFF0A" }} />

          {/* Type breakdown mini chart */}
          <div>
            <span
              className="text-[10px] uppercase block mb-2.5"
              style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif", letterSpacing: "0.06em" }}
            >
              Distribution
            </span>
            <div className="flex flex-col gap-1.5">
              {ALL_TYPES.map((type) => {
                const color = EVENT_TYPE_COLOR[type];
                const count = events.filter((e) => e.type === type).length;
                const pct = events.length > 0 ? (count / events.length) * 100 : 0;
                return (
                  <div key={type} className="flex flex-col gap-0.5">
                    <div className="flex items-center justify-between">
                      <span
                        className="text-[10px]"
                        style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}
                      >
                        {EVENT_TYPE_LABEL[type]}
                      </span>
                      <span
                        className="text-[10px]"
                        style={{ color: "#4E5060", fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)" }}
                      >
                        {pct.toFixed(0)}%
                      </span>
                    </div>
                    <div
                      className="h-1 rounded-full overflow-hidden"
                      style={{ backgroundColor: "#FFFFFF08" }}
                    >
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{ width: `${pct}%`, backgroundColor: color }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Bottom stats bar */}
      <div
        className="shrink-0 rounded-[10px] px-5 py-3 flex items-center gap-6"
        style={{ backgroundColor: "#111318", border: "1px solid #FFFFFF0A" }}
      >
        {/* Events/min */}
        <div className="flex items-center gap-2">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M6 1L7.5 4.5H11L8 7L9 10.5L6 8.5L3 10.5L4 7L1 4.5H4.5L6 1Z" fill="#E8A44A" opacity="0.7" />
          </svg>
          <span
            className="text-[11px]"
            style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}
          >
            Rate
          </span>
          <span
            className="text-[13px] font-medium"
            style={{ color: "#ECECEE", fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)" }}
          >
            {eventsPerMin}
          </span>
          <span
            className="text-[11px]"
            style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif" }}
          >
            events/min
          </span>
        </div>

        {/* Divider */}
        <div style={{ width: "1px", height: "16px", backgroundColor: "#FFFFFF0A" }} />

        {/* Most active agent */}
        <div className="flex items-center gap-2">
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{ backgroundColor: "#4ADE80" }}
          />
          <span
            className="text-[11px]"
            style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}
          >
            Most active
          </span>
          <span
            className="text-[12px]"
            style={{ color: "#A0A0AA", fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)" }}
          >
            {mostActiveAgent}
          </span>
          {mostActiveAgent !== "—" && (
            <span
              className="text-[11px] px-1.5 py-0.5 rounded-full"
              style={{
                backgroundColor: "#4ADE8010",
                color: "#4ADE80",
                fontFamily: "'Inter', sans-serif",
              }}
            >
              {agentCounts[mostActiveAgent]} events
            </span>
          )}
        </div>

        {/* Divider */}
        <div style={{ width: "1px", height: "16px", backgroundColor: "#FFFFFF0A" }} />

        {/* Filtered vs total */}
        <div className="flex items-center gap-2">
          <span
            className="text-[11px]"
            style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif" }}
          >
            Displaying
          </span>
          <span
            className="text-[12px]"
            style={{ color: "#A0A0AA", fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)" }}
          >
            {filtered.length} / {events.length}
          </span>
          <span
            className="text-[11px]"
            style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif" }}
          >
            events
          </span>
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* New event every 3s indicator */}
        <div className="flex items-center gap-1.5">
          <span
            className="w-1.5 h-1.5 rounded-full animate-pulse"
            style={{ backgroundColor: "#5B8DEF" }}
          />
          <span
            className="text-[11px]"
            style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif" }}
          >
            Polling every 3s
          </span>
        </div>
      </div>
    </div>
  );
}
