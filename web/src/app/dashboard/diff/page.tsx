"use client";

import { useEffect, useMemo, useState } from "react";
import {
  api,
  getDemoData,
  getDemoDiff,
  USE_DEMO_DATA,
} from "@/lib/api";
import type { Commit, StateDiff } from "@/lib/api";
import { truncateHash, formatTimestamp } from "@/lib/utils";
import { DiffPanel } from "./components";

export default function DiffPage() {
  const [commits, setCommits] = useState<Commit[]>(
    USE_DEMO_DATA ? getDemoData().commits : []
  );
  const [loading, setLoading] = useState(!USE_DEMO_DATA);
  const [hash1, setHash1] = useState("");
  const [hash2, setHash2] = useState("");
  const [diff, setDiff] = useState<StateDiff | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);

  useEffect(() => {
    if (USE_DEMO_DATA) return;
    let live = true;
    api
      .getCommits()
      .then((r) => { if (live) setCommits(r.commits); })
      .catch(() => { if (USE_DEMO_DATA) setCommits(getDemoData().commits); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, []);

  // Pre-select two most recent commits
  useEffect(() => {
    if (commits.length >= 2 && !hash1 && !hash2) {
      const sorted = [...commits].sort(
        (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
      );
      setHash1(sorted[1].hash);
      setHash2(sorted[0].hash);
    }
  }, [commits, hash1, hash2]);

  const sortedCommits = useMemo(
    () => [...commits].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()),
    [commits]
  );

  function handleCompare() {
    if (!hash1 || !hash2) return;
    setDiffLoading(true);
    if (USE_DEMO_DATA) {
      setDiff(getDemoDiff(hash1, hash2));
      setDiffLoading(false);
    } else {
      api
        .getDiff(hash1, hash2)
        .then(setDiff)
        .catch(() => setDiff(null))
        .finally(() => setDiffLoading(false));
    }
  }

  // Auto-compare on first load with pre-selected commits
  useEffect(() => {
    if (hash1 && hash2 && !diff && !diffLoading) {
      handleCompare();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hash1, hash2]);

  return (
    <div className="flex flex-col gap-5 h-full">
      {/* Header */}
      <div>
        <span
          className="text-[18px] font-semibold block"
          style={{
            color: "#ECECEE",
            fontFamily: "var(--font-display, 'Space Grotesk', sans-serif)",
            lineHeight: "22px",
          }}
        >
          Diff Viewer
        </span>
        <span className="text-[12px] mt-1 block" style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}>
          Compare state between any two commits
        </span>
      </div>

      {/* Commit selectors */}
      <div
        className="flex items-end gap-3 p-5 rounded-[10px]"
        style={{ backgroundColor: "#111318", border: "1px solid #FFFFFF0A" }}
      >
        {/* Base commit */}
        <div className="flex flex-col gap-1.5 flex-1">
          <span
            className="text-[10px] uppercase"
            style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif", letterSpacing: "0.06em" }}
          >
            Base commit
          </span>
          <select
            value={hash1}
            onChange={(e) => setHash1(e.target.value)}
            className="text-[12px] py-2 px-3 rounded-[6px] outline-none w-full"
            style={{
              backgroundColor: "#FFFFFF08",
              border: "1px solid #FFFFFF0A",
              color: "#ECECEE",
              fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
            }}
          >
            <option value="">Select commit…</option>
            {sortedCommits.map((c) => (
              <option key={c.hash} value={c.hash}>
                {truncateHash(c.hash)} — {c.message}
              </option>
            ))}
          </select>
        </div>

        {/* Arrow */}
        <div className="flex items-center justify-center pb-2">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M4 10h12M12 6l4 4-4 4" stroke="#4E5060" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>

        {/* Target commit */}
        <div className="flex flex-col gap-1.5 flex-1">
          <span
            className="text-[10px] uppercase"
            style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif", letterSpacing: "0.06em" }}
          >
            Target commit
          </span>
          <select
            value={hash2}
            onChange={(e) => setHash2(e.target.value)}
            className="text-[12px] py-2 px-3 rounded-[6px] outline-none w-full"
            style={{
              backgroundColor: "#FFFFFF08",
              border: "1px solid #FFFFFF0A",
              color: "#ECECEE",
              fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
            }}
          >
            <option value="">Select commit…</option>
            {sortedCommits.map((c) => (
              <option key={c.hash} value={c.hash}>
                {truncateHash(c.hash)} — {c.message}
              </option>
            ))}
          </select>
        </div>

        {/* Compare button */}
        <button
          onClick={handleCompare}
          disabled={!hash1 || !hash2 || hash1 === hash2}
          className="py-2 px-5 rounded-[6px] text-[12px] font-medium shrink-0 transition-opacity"
          style={{
            backgroundColor: hash1 && hash2 && hash1 !== hash2 ? "#ECECEE" : "#FFFFFF14",
            color: hash1 && hash2 && hash1 !== hash2 ? "#0C0D10" : "#4E5060",
            fontFamily: "'Inter', sans-serif",
            opacity: hash1 && hash2 && hash1 !== hash2 ? 1 : 0.5,
          }}
        >
          Compare
        </button>
      </div>

      {/* Commit info row */}
      {hash1 && hash2 && diff && (
        <div className="flex items-center gap-3">
          <CommitChip hash={hash1} commits={commits} side="base" />
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M3 8h10M10 5l3 3-3 3" stroke="#4E5060" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <CommitChip hash={hash2} commits={commits} side="target" />
        </div>
      )}

      {/* Loading */}
      {diffLoading && (
        <div
          className="flex items-center justify-center py-12 rounded-[10px]"
          style={{ backgroundColor: "#111318", border: "1px solid #FFFFFF0A" }}
        >
          <span className="text-[13px]" style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}>
            Computing diff…
          </span>
        </div>
      )}

      {/* Diff results */}
      {diff && !diffLoading && <DiffPanel diff={diff} />}

      {/* Empty state */}
      {!diff && !diffLoading && (
        <div
          className="flex flex-col items-center justify-center py-16 rounded-[10px] flex-1"
          style={{ backgroundColor: "#111318", border: "1px solid #FFFFFF0A" }}
        >
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none" className="mb-3">
            <rect x="2" y="2" width="28" height="28" rx="6" stroke="#FFFFFF14" strokeWidth="2" />
            <line x1="10" y1="12" x2="22" y2="12" stroke="#FFFFFF14" strokeWidth="2" strokeLinecap="round" />
            <line x1="10" y1="16" x2="18" y2="16" stroke="#FFFFFF14" strokeWidth="2" strokeLinecap="round" />
            <line x1="10" y1="20" x2="14" y2="20" stroke="#FFFFFF14" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <span className="text-[13px]" style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif" }}>
            Select two commits and click Compare
          </span>
        </div>
      )}
    </div>
  );
}

function CommitChip({
  hash,
  commits,
  side,
}: {
  hash: string;
  commits: Commit[];
  side: "base" | "target";
}) {
  const commit = commits.find((c) => c.hash === hash);
  if (!commit) return null;

  return (
    <div
      className="flex items-center gap-2 px-3 py-1.5 rounded-lg"
      style={{ backgroundColor: "#FFFFFF08", border: "1px solid #FFFFFF0A" }}
    >
      <span
        className="text-[10px] uppercase"
        style={{
          color: side === "base" ? "#E85D5D" : "#4ADE80",
          fontFamily: "'Inter', sans-serif",
          letterSpacing: "0.04em",
        }}
      >
        {side}
      </span>
      <span
        className="text-[11px]"
        style={{ color: "#5B8DEF", fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)" }}
      >
        {truncateHash(hash)}
      </span>
      <span className="text-[11px] truncate" style={{ color: "#A0A0AA", fontFamily: "'Inter', sans-serif", maxWidth: "200px" }}>
        {commit.message}
      </span>
      <span className="text-[10px]" style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif" }}>
        {formatTimestamp(commit.timestamp).split(",").pop()?.trim()}
      </span>
    </div>
  );
}
