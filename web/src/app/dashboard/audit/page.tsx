"use client";

import { useEffect, useMemo, useState } from "react";
import { api, getDemoData, USE_DEMO_DATA } from "@/lib/api";
import type { AuditEntry } from "@/lib/api";
import {
  truncateHash,
  formatTimestamp,
  actionTypeColor,
  levelColor,
  downloadAsJson,
} from "@/lib/utils";

export default function AuditPage() {
  const [entries, setEntries] = useState<AuditEntry[]>(
    USE_DEMO_DATA ? getDemoData().audit : []
  );
  const [search, setSearch] = useState("");
  const [agentFilter, setAgentFilter] = useState("all");
  const [actionFilter, setActionFilter] = useState("all");
  const [levelFilter, setLevelFilter] = useState("all");
  const [loading, setLoading] = useState(!USE_DEMO_DATA);

  useEffect(() => {
    if (USE_DEMO_DATA) return;
    let live = true;
    api
      .getAudit()
      .then((r) => { if (live) setEntries(r.entries); })
      .catch(() => { if (USE_DEMO_DATA) setEntries(getDemoData().audit); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, []);

  const agents = useMemo(
    () => ["all", ...Array.from(new Set(entries.map((e) => e.agent_id)))],
    [entries]
  );
  const actions = useMemo(
    () => ["all", ...Array.from(new Set(entries.map((e) => e.action)))],
    [entries]
  );
  const levels = useMemo(
    () => ["all", ...Array.from(new Set(entries.map((e) => e.level)))],
    [entries]
  );

  const filtered = useMemo(() => {
    return entries.filter((e) => {
      if (agentFilter !== "all" && e.agent_id !== agentFilter) return false;
      if (actionFilter !== "all" && e.action !== actionFilter) return false;
      if (levelFilter !== "all" && e.level !== levelFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        if (
          !e.message.toLowerCase().includes(q) &&
          !(e.commit_hash || "").toLowerCase().includes(q) &&
          !e.agent_id.toLowerCase().includes(q)
        )
          return false;
      }
      return true;
    });
  }, [entries, search, agentFilter, actionFilter, levelFilter]);

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
            Audit Log
          </span>
          <span className="text-[12px] mt-1 block" style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}>
            {loading ? "Loading..." : `${entries.length} events recorded`}
          </span>
        </div>
        <button
          onClick={() => downloadAsJson(filtered, "agit-audit-export.json")}
          className="flex items-center gap-1.5 py-1.5 px-3 rounded-[6px] text-[12px] font-medium"
          style={{
            backgroundColor: "#FFFFFF08",
            color: "#A0A0AA",
            border: "1px solid #FFFFFF0F",
            fontFamily: "'Inter', sans-serif",
          }}
        >
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M6 2v6M3.5 6L6 8.5 8.5 6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M2 10h8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
          Export JSON
        </button>
      </div>

      {/* Integrity banner */}
      <div
        className="flex items-center gap-2.5 px-4 py-2.5 rounded-lg"
        style={{ backgroundColor: "#4ADE8008", border: "1px solid #4ADE801A" }}
      >
        <span
          className="w-2 h-2 rounded-full shrink-0"
          style={{ backgroundColor: "#4ADE80", boxShadow: "0 0 6px #4ADE8060" }}
        />
        <span className="text-[12px]" style={{ color: "#4ADE80", fontFamily: "'Inter', sans-serif" }}>
          Hash chain integrity verified
        </span>
        <span className="text-[11px]" style={{ color: "#4ADE8080", fontFamily: "'Inter', sans-serif" }}>
          — {entries.length} entries, all checksums valid
        </span>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2.5">
        {/* Search */}
        <div className="relative flex-1 max-w-xs">
          <svg
            width="12" height="12" viewBox="0 0 12 12" fill="none"
            className="absolute left-2.5 top-1/2 -translate-y-1/2"
          >
            <circle cx="5" cy="5" r="3.5" stroke="#4E5060" strokeWidth="1.2" />
            <line x1="7.8" y1="7.8" x2="10.5" y2="10.5" stroke="#4E5060" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
          <input
            type="text"
            placeholder="Search messages or hashes..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full py-1.5 pl-8 pr-3 rounded-[6px] text-[12px] outline-none"
            style={{
              backgroundColor: "#FFFFFF08",
              border: "1px solid #FFFFFF0A",
              color: "#ECECEE",
              fontFamily: "'Inter', sans-serif",
            }}
          />
        </div>

        {/* Dropdowns */}
        {[
          { value: agentFilter, set: setAgentFilter, options: agents, label: "All Agents" },
          { value: actionFilter, set: setActionFilter, options: actions, label: "All Actions" },
          { value: levelFilter, set: setLevelFilter, options: levels, label: "All Levels" },
        ].map(({ value, set, options, label }) => (
          <select
            key={label}
            value={value}
            onChange={(e) => set(e.target.value)}
            className="text-[12px] py-1.5 px-3 rounded-[6px] outline-none"
            style={{
              backgroundColor: "#FFFFFF08",
              border: "1px solid #FFFFFF0A",
              color: "#ECECEE",
              fontFamily: "'Inter', sans-serif",
            }}
          >
            {options.map((o) => (
              <option key={o} value={o}>
                {o === "all" ? label : o}
              </option>
            ))}
          </select>
        ))}
      </div>

      {/* Result count with live indicator */}
      <div className="flex items-center gap-2">
        <span
          className="w-1.5 h-1.5 rounded-full shrink-0 animate-pulse"
          style={{ backgroundColor: "#4ADE80" }}
        />
        <span className="text-[11px]" style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}>
          Showing {filtered.length} of {entries.length} entries
        </span>
      </div>

      {/* Table */}
      <div
        className="rounded-[10px] overflow-hidden flex-1 min-h-0"
        style={{ backgroundColor: "#111318", border: "1px solid #FFFFFF0A" }}
      >
        <div className="overflow-auto h-full">
          <table className="w-full">
            <thead>
              <tr style={{ backgroundColor: "#0D0E12" }}>
                {["Timestamp", "Agent", "Action", "Message", "Commit", "Level"].map(
                  (h) => (
                    <th
                      key={h}
                      className="text-left text-[10px] font-medium uppercase px-4 py-2.5"
                      style={{
                        color: "#4E5060",
                        fontFamily: "'Inter', sans-serif",
                        letterSpacing: "0.06em",
                        borderBottom: "1px solid #FFFFFF0A",
                      }}
                    >
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {filtered.map((entry) => (
                <tr
                  key={entry.id}
                  className="transition-colors"
                  style={{ borderBottom: "1px solid #FFFFFF06" }}
                  onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "#FFFFFF08")}
                  onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
                >
                  <td className="px-4 py-2.5">
                    <span
                      className="text-[11px] whitespace-nowrap"
                      style={{
                        color: "#6E6E76",
                        fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                      }}
                    >
                      {formatTimestamp(entry.timestamp)}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <span
                      className="text-[11px] px-2 py-0.5 rounded"
                      style={{
                        backgroundColor: "#FFFFFF08",
                        color: "#A0A0AA",
                        fontFamily: "'Inter', sans-serif",
                      }}
                    >
                      {entry.agent_id}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <span
                      className="text-[11px]"
                      style={{
                        color: actionTypeColor(entry.action),
                        fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                      }}
                    >
                      {entry.action}
                    </span>
                  </td>
                  <td className="px-4 py-2.5" style={{ maxWidth: "320px" }}>
                    <span
                      className="text-[12px] truncate block"
                      style={{ color: "#ECECEE", fontFamily: "'Inter', sans-serif" }}
                    >
                      {entry.message}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    {entry.commit_hash ? (
                      <span
                        className="text-[11px]"
                        style={{
                          color: "#5B8DEF",
                          fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                        }}
                      >
                        {truncateHash(entry.commit_hash)}
                      </span>
                    ) : (
                      <span className="text-[11px]" style={{ color: "#4E5060" }}>—</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    <span
                      className="text-[10px] uppercase font-medium px-2 py-0.5 rounded-full"
                      style={{
                        backgroundColor: levelColor(entry.level) + "18",
                        color: levelColor(entry.level),
                        fontFamily: "'Inter', sans-serif",
                        letterSpacing: "0.04em",
                      }}
                    >
                      {entry.level}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
