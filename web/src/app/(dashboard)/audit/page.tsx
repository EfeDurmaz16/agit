"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, getDemoData, USE_DEMO_DATA } from "@/lib/api";
import { truncateHash, formatTimestamp } from "@/lib/utils";

export default function AuditPage() {
  const [entries, setEntries] = useState(
    USE_DEMO_DATA ? getDemoData().audit : []
  );
  const [search, setSearch] = useState("");
  const [agentFilter, setAgentFilter] = useState<string>("all");
  const [actionFilter, setActionFilter] = useState<string>("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    api
      .getAudit()
      .then((res) => {
        if (!isMounted) return;
        setEntries(res.entries);
      })
      .catch(() => {
        if (USE_DEMO_DATA) {
          setEntries(getDemoData().audit);
        }
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  const agents = useMemo(
    () => ["all", ...new Set(entries.map((e) => e.agent_id))],
    [entries]
  );
  const actions = useMemo(
    () => ["all", ...new Set(entries.map((e) => e.action))],
    [entries]
  );

  const filtered = useMemo(() => {
    return entries.filter((e) => {
      if (agentFilter !== "all" && e.agent_id !== agentFilter) return false;
      if (actionFilter !== "all" && e.action !== actionFilter) return false;
      if (
        search &&
        !e.message.toLowerCase().includes(search.toLowerCase()) &&
        !(e.commit_hash || "").toLowerCase().includes(search.toLowerCase())
      )
        return false;
      return true;
    });
  }, [entries, search, agentFilter, actionFilter]);

  const levelBadge = (level: string) => {
    if (level === "warning") return "warning" as const;
    if (level === "error") return "destructive" as const;
    return "default" as const;
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-stone-900">
            Audit Log
          </h1>
          <p className="text-sm text-stone-500 mt-1">
            {loading ? "Loading audit events..." : `${entries.length} events recorded`}
          </p>
        </div>
        <Button variant="outline" size="sm">
          Export
        </Button>
      </div>

      {/* Search + Filters */}
      <div className="flex items-center gap-3 mb-6">
        <div className="relative flex-1 max-w-sm">
          <svg
            width="14"
            height="14"
            viewBox="0 0 16 16"
            fill="none"
            className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400"
          >
            <circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.5" />
            <line x1="11" y1="11" x2="14" y2="14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <input
            type="text"
            placeholder="Search messages or hashes..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 text-sm bg-white border border-stone-200 rounded-lg text-stone-900 placeholder:text-stone-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-500 transition-shadow"
          />
        </div>

        <select
          value={agentFilter}
          onChange={(e) => setAgentFilter(e.target.value)}
          className="text-sm bg-white border border-stone-200 rounded-lg px-3 py-2 text-stone-700 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
        >
          {agents.map((a) => (
            <option key={a} value={a}>
              {a === "all" ? "All Agents" : a}
            </option>
          ))}
        </select>

        <select
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
          className="text-sm bg-white border border-stone-200 rounded-lg px-3 py-2 text-stone-700 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
        >
          {actions.map((a) => (
            <option key={a} value={a}>
              {a === "all" ? "All Actions" : a}
            </option>
          ))}
        </select>
      </div>

      <p className="text-xs text-stone-400 mb-3">
        Showing {filtered.length} of {entries.length} entries
      </p>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-stone-200 bg-stone-50/50">
                  {["Timestamp", "Agent", "Action", "Message", "Commit", "Level"].map(
                    (h) => (
                      <th
                        key={h}
                        className="text-left text-[11px] font-medium text-stone-400 uppercase tracking-wider px-5 py-3"
                      >
                        {h}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {filtered.map((entry) => (
                  <tr
                    key={entry.id}
                    className="hover:bg-stone-50/50 transition-colors"
                  >
                    <td className="px-5 py-3 text-xs text-stone-500 font-mono whitespace-nowrap">
                      {formatTimestamp(entry.timestamp)}
                    </td>
                    <td className="px-5 py-3">
                      <span className="text-xs font-medium text-stone-700 bg-stone-100 px-2 py-0.5 rounded-md">
                        {entry.agent_id}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-xs font-mono text-stone-500">
                      {entry.action}
                    </td>
                    <td className="px-5 py-3 text-sm text-stone-700 max-w-xs truncate">
                      {entry.message}
                    </td>
                    <td className="px-5 py-3">
                      {entry.commit_hash && (
                        <code className="text-xs font-mono text-stone-400 bg-stone-50 px-1.5 py-0.5 rounded">
                          {truncateHash(entry.commit_hash)}
                        </code>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      <Badge variant={levelBadge(entry.level)}>
                        {entry.level}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
