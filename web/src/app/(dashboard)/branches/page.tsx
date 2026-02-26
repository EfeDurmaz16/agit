"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api, getDemoData, USE_DEMO_DATA } from "@/lib/api";
import { truncateHash } from "@/lib/utils";

export default function BranchesPage() {
  const [branches, setBranches] = useState(
    USE_DEMO_DATA ? getDemoData().branches : []
  );
  const graphCommits = USE_DEMO_DATA ? getDemoData().commits : [];
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    api
      .getBranches()
      .then((res) => {
        if (!isMounted) return;
        setBranches(res.branches);
      })
      .catch(() => {
        if (USE_DEMO_DATA) {
          setBranches(getDemoData().branches);
        }
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-stone-900">
          Branches
        </h1>
        <p className="text-sm text-stone-500 mt-1">
          {loading ? "Loading branches..." : `${branches.length} branches in repository`}
        </p>
      </div>

      {/* Branch list */}
      <div className="space-y-3">
        {branches.map((branch) => (
          <Card
            key={branch.name}
            className={
              branch.is_current ? "border-emerald-200 bg-emerald-50/30" : ""
            }
          >
            <CardContent className="py-4 px-5">
              <div className="flex items-center gap-4">
                <div
                  className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${
                    branch.is_current ? "bg-emerald-100" : "bg-stone-100"
                  }`}
                >
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 16 16"
                    fill="none"
                    className={
                      branch.is_current ? "text-emerald-600" : "text-stone-400"
                    }
                  >
                    <circle cx="4" cy="4" r="2" stroke="currentColor" strokeWidth="1.5" />
                    <circle cx="4" cy="12" r="2" stroke="currentColor" strokeWidth="1.5" />
                    <circle cx="12" cy="8" r="2" stroke="currentColor" strokeWidth="1.5" />
                    <line x1="4" y1="6" x2="4" y2="10" stroke="currentColor" strokeWidth="1.5" />
                    <path d="M4 6 C 4 8 8 8 10 8" stroke="currentColor" strokeWidth="1.5" fill="none" />
                  </svg>
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2.5">
                    <span className="text-sm font-medium text-stone-900 font-mono">
                      {branch.name}
                    </span>
                    {branch.is_current && (
                      <Badge variant="emerald">current</Badge>
                    )}
                    {branch.name.startsWith("retry/") && (
                      <Badge variant="warning">retry</Badge>
                    )}
                    {branch.name.startsWith("feature/") && (
                      <Badge variant="outline">feature</Badge>
                    )}
                  </div>
                  <span className="text-xs text-stone-400 mt-1 block">
                    HEAD at{" "}
                    <code className="font-mono text-stone-500">
                      {truncateHash(branch.hash)}
                    </code>
                  </span>
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  {branch.is_current ? (
                    <>
                      <div className="w-3 h-3 rounded-full bg-emerald-500" />
                      <div className="w-12 h-0.5 bg-emerald-300 rounded" />
                      <div className="w-2 h-2 rounded-full bg-emerald-300" />
                    </>
                  ) : (
                    <>
                      <div className="w-2 h-2 rounded-full bg-stone-300" />
                      <div className="w-8 h-0.5 bg-stone-200 rounded" />
                      <div className="w-2 h-2 rounded-full bg-stone-200" />
                    </>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* ASCII branch graph */}
      <Card className="mt-8">
        <CardContent className="pt-5">
          <p className="text-xs font-medium text-stone-400 uppercase tracking-wider mb-4">
            Branch Graph
          </p>
          <div className="font-mono text-xs text-stone-500 leading-7 bg-stone-50 rounded-lg p-4 border border-stone-100">
            <div className="flex items-center gap-2">
              <span className="text-emerald-600 font-bold">*</span>
              <span className="text-stone-300">|</span>
              <span className="text-stone-400">{truncateHash(branches[0]?.hash || "")}</span>
              <span className="text-stone-700">weather API response</span>
              <span className="text-emerald-600 font-medium">(main)</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-emerald-600 font-bold">*</span>
              <span className="text-stone-300">|</span>
              <span className="text-stone-400">{truncateHash(graphCommits[1]?.hash || "")}</span>
              <span className="text-stone-700">calling weather API</span>
            </div>
            <div className="flex items-center gap-2 ml-3">
              <span className="text-amber-500">&#92;</span>
              <span className="text-stone-300">|</span>
              <span className="text-stone-400">{truncateHash(branches[1]?.hash || "")}</span>
              <span className="text-stone-700">retry attempt 1</span>
              <span className="text-amber-500 font-medium">(retry/a1b2c3/attempt-1)</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-emerald-600 font-bold">*</span>
              <span className="text-stone-300">|</span>
              <span className="text-stone-400">{truncateHash(graphCommits[2]?.hash || "")}</span>
              <span className="text-stone-700">user input received</span>
            </div>
            <div className="flex items-center gap-2 ml-3">
              <span className="text-blue-500">&#92;</span>
              <span className="text-stone-300">|</span>
              <span className="text-stone-400">{truncateHash(branches[2]?.hash || "")}</span>
              <span className="text-stone-700">summary generated</span>
              <span className="text-blue-500 font-medium">(feature/summarize)</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
