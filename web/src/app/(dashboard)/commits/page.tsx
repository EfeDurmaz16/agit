"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, getDemoData, USE_DEMO_DATA } from "@/lib/api";
import { truncateHash, formatTimestamp } from "@/lib/utils";

const actionBadgeVariant = (action: string) => {
  if (action === "tool_call" || action === "llm_response") return "emerald" as const;
  if (action === "rollback") return "destructive" as const;
  if (action === "checkpoint") return "outline" as const;
  return "default" as const;
};

export default function CommitsPage() {
  const [commits, setCommits] = useState(
    USE_DEMO_DATA ? getDemoData().commits : []
  );
  const [expandedHash, setExpandedHash] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    api
      .getCommits()
      .then((res) => {
        if (!isMounted) return;
        setCommits(res.commits);
      })
      .catch(() => {
        if (USE_DEMO_DATA) {
          setCommits(getDemoData().commits);
        }
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  const actionTypes = ["all", ...new Set(commits.map((c) => c.action_type))];
  const filtered =
    filter === "all" ? commits : commits.filter((c) => c.action_type === filter);

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-stone-900">
            Commits
          </h1>
          <p className="text-sm text-stone-500 mt-1">
            {loading ? "Loading commits..." : `${commits.length} commits across all branches`}
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-1.5 mb-6">
        {actionTypes.map((type) => (
          <Button
            key={type}
            variant={filter === type ? "default" : "ghost"}
            size="sm"
            onClick={() => setFilter(type)}
            className="capitalize"
          >
            {type === "all" ? "All" : type.replace("_", " ")}
          </Button>
        ))}
      </div>

      {/* Commit list */}
      <Card>
        <CardContent className="p-0">
          <div className="divide-y divide-stone-100">
            {filtered.map((commit, idx) => {
              const isExpanded = expandedHash === commit.hash;
              return (
                <div key={commit.hash}>
                  <button
                    onClick={() =>
                      setExpandedHash(isExpanded ? null : commit.hash)
                    }
                    className="w-full text-left px-5 py-3.5 hover:bg-stone-50/50 transition-colors flex items-center gap-4"
                  >
                    {/* Timeline dot */}
                    <div className="flex flex-col items-center shrink-0">
                      <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 ring-4 ring-emerald-50" />
                      {idx < filtered.length - 1 && (
                        <div className="w-px h-4 bg-stone-200 mt-1" />
                      )}
                    </div>

                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-stone-800 truncate">
                        {commit.message}
                      </p>
                      <div className="flex items-center gap-3 mt-1">
                        <span className="text-xs text-stone-400 font-mono">
                          {commit.author}
                        </span>
                        <span className="text-xs text-stone-300">&middot;</span>
                        <span className="text-xs text-stone-400">
                          {formatTimestamp(commit.timestamp)}
                        </span>
                      </div>
                    </div>

                    <Badge variant={actionBadgeVariant(commit.action_type)}>
                      {commit.action_type}
                    </Badge>

                    <code className="text-xs font-mono text-stone-400 bg-stone-50 px-2 py-1 rounded-md shrink-0">
                      {truncateHash(commit.hash)}
                    </code>

                    <svg
                      width="16"
                      height="16"
                      viewBox="0 0 16 16"
                      fill="none"
                      className={`text-stone-300 transition-transform shrink-0 ${isExpanded ? "rotate-180" : ""}`}
                    >
                      <path
                        d="M4 6L8 10L12 6"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </button>

                  {isExpanded && (
                    <div className="px-5 pb-4 ml-10 border-l-2 border-emerald-100">
                      <div className="bg-stone-50 rounded-lg p-4 space-y-3">
                        <DetailRow label="Full Hash" mono>
                          {commit.hash}
                        </DetailRow>
                        <DetailRow label="Author">{commit.author}</DetailRow>
                        <DetailRow label="Action Type">
                          {commit.action_type}
                        </DetailRow>
                        <DetailRow label="Timestamp">
                          {commit.timestamp}
                        </DetailRow>
                        <DetailRow label="Parents" mono>
                          {commit.parent_hashes.length > 0
                            ? commit.parent_hashes.join(", ")
                            : "none (root commit)"}
                        </DetailRow>

                        <div className="pt-2 border-t border-stone-200">
                          <p className="text-[11px] uppercase tracking-wider text-stone-400 mb-2">
                            State Preview
                          </p>
                          <pre className="text-xs font-mono text-stone-600 bg-white rounded-md p-3 border border-stone-200 overflow-x-auto">
                            {JSON.stringify(
                              {
                                memory: {
                                  message: commit.message,
                                  action: commit.action_type,
                                },
                                world_state: { branch: "main" },
                              },
                              null,
                              2
                            )}
                          </pre>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function DetailRow({
  label,
  children,
  mono,
}: {
  label: string;
  children: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-start gap-3">
      <span className="text-xs text-stone-400 w-24 shrink-0 pt-0.5">
        {label}
      </span>
      <span
        className={`text-xs text-stone-700 break-all ${mono ? "font-mono" : ""}`}
      >
        {children}
      </span>
    </div>
  );
}
