"use client";

import { useEffect, useMemo, useState } from "react";
import { api, getDemoData, USE_DEMO_DATA } from "@/lib/api";
import type { Branch, Commit } from "@/lib/api";
import { truncateHash } from "@/lib/utils";

const BRANCH_COLORS: Record<string, string> = {
  default: "#4ADE80",
  retry: "#E8A44A",
  feature: "#5B8DEF",
  rollback: "#E85D5D",
};

function branchColor(b: Branch): string {
  if (b.type && BRANCH_COLORS[b.type]) return BRANCH_COLORS[b.type];
  if (b.name.startsWith("retry/")) return BRANCH_COLORS.retry;
  if (b.name.startsWith("feature/") || b.name.startsWith("experiment/")) return BRANCH_COLORS.feature;
  if (b.name.startsWith("rollback/")) return BRANCH_COLORS.rollback;
  return BRANCH_COLORS.default;
}

// ---------------------------------------------------------------------------
// SVG Branch Graph
// ---------------------------------------------------------------------------
const GRAPH_ROW = 40;
const GRAPH_LANE = 30;
const GRAPH_PAD = 20;
const GRAPH_NODE_R = 5;

function BranchGraph({
  branches,
  commits,
}: {
  branches: Branch[];
  commits: Commit[];
}) {
  // Build simple layout: main is lane 0, other branches get subsequent lanes
  const branchOrder = ["main", ...branches.filter((b) => !b.is_current).map((b) => b.name)];
  const laneMap = new Map(branchOrder.map((name, i) => [name, i]));

  // Get commits per branch
  const branchCommits = new Map<string, Commit[]>();
  for (const c of commits) {
    const bName = c.branch || "main";
    if (!branchCommits.has(bName)) branchCommits.set(bName, []);
    branchCommits.get(bName)!.push(c);
  }

  const mainCommits = (branchCommits.get("main") || []).sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );

  const svgW = GRAPH_PAD * 2 + branchOrder.length * GRAPH_LANE + 200;
  const svgH = GRAPH_PAD * 2 + Math.max(mainCommits.length, 4) * GRAPH_ROW;

  const elements: React.ReactNode[] = [];

  // Draw main trunk
  const mainLane = 0;
  const mx = GRAPH_PAD + mainLane * GRAPH_LANE + GRAPH_LANE / 2;
  if (mainCommits.length > 1) {
    elements.push(
      <line
        key="main-trunk"
        x1={mx} y1={GRAPH_PAD + GRAPH_NODE_R}
        x2={mx} y2={GRAPH_PAD + (mainCommits.length - 1) * GRAPH_ROW}
        stroke="#4ADE80"
        strokeWidth="2"
        strokeOpacity="0.4"
      />
    );
  }

  // Main commit nodes
  mainCommits.forEach((c, i) => {
    const cy = GRAPH_PAD + i * GRAPH_ROW;
    elements.push(
      <circle
        key={`main-${c.hash}`}
        cx={mx} cy={cy} r={GRAPH_NODE_R}
        fill="#4ADE80"
        stroke="#0C0D10"
        strokeWidth="2"
      />
    );
  });

  // Draw branch paths
  branches.forEach((branch) => {
    if (branch.name === "main") return;
    const lane = laneMap.get(branch.name) ?? 1;
    const bx = GRAPH_PAD + lane * GRAPH_LANE + GRAPH_LANE / 2;
    const color = branchColor(branch);
    const bCommits = (branchCommits.get(branch.name) || []).sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );
    if (bCommits.length === 0) return;

    // Find fork point (parent in main)
    const forkIdx = Math.max(1, Math.min(lane, mainCommits.length - 1));
    const forkY = GRAPH_PAD + forkIdx * GRAPH_ROW;

    // Branch line
    const branchStartY = forkY + 10;
    const branchEndY = branchStartY + (bCommits.length - 1) * GRAPH_ROW * 0.6 + 20;

    // Curve from main to branch lane
    elements.push(
      <path
        key={`branch-path-${branch.name}`}
        d={`M${mx},${forkY} Q${mx},${branchStartY - 5} ${bx},${branchStartY}`}
        stroke={color}
        strokeWidth="1.5"
        strokeOpacity="0.4"
        fill="none"
      />
    );

    // Vertical line for branch
    if (bCommits.length > 1) {
      elements.push(
        <line
          key={`branch-line-${branch.name}`}
          x1={bx} y1={branchStartY}
          x2={bx} y2={branchEndY}
          stroke={color}
          strokeWidth="1.5"
          strokeOpacity="0.3"
        />
      );
    }

    // Branch commit nodes
    bCommits.forEach((c, i) => {
      const cy = branchStartY + i * GRAPH_ROW * 0.6;
      elements.push(
        <circle
          key={`branch-node-${c.hash}`}
          cx={bx} cy={cy} r={4}
          fill={color}
          stroke="#0C0D10"
          strokeWidth="1.5"
        />
      );
    });

    // Branch label
    const labelY = branchStartY + (bCommits.length - 1) * GRAPH_ROW * 0.6 + 16;
    elements.push(
      <text
        key={`branch-label-${branch.name}`}
        x={bx}
        y={labelY}
        textAnchor="middle"
        style={{
          fontSize: "9px",
          fill: color,
          fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
        }}
      >
        {branch.name.length > 20 ? branch.name.slice(0, 18) + "…" : branch.name}
      </text>
    );
  });

  return (
    <div className="overflow-auto" style={{ maxHeight: "320px" }}>
      <svg width={svgW} height={svgH} viewBox={`0 0 ${svgW} ${svgH}`}>
        {elements}
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function BranchesPage() {
  const [branches, setBranches] = useState<Branch[]>(
    USE_DEMO_DATA ? getDemoData().branches : []
  );
  const [commits] = useState<Commit[]>(USE_DEMO_DATA ? getDemoData().commits : []);
  const [loading, setLoading] = useState(!USE_DEMO_DATA);
  const [compareBranches, setCompareBranches] = useState<[string, string]>(["", ""]);

  useEffect(() => {
    if (USE_DEMO_DATA) return;
    let live = true;
    api
      .getBranches()
      .then((r) => { if (live) setBranches(r.branches); })
      .catch(() => { if (USE_DEMO_DATA) setBranches(getDemoData().branches); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, []);

  // Branch comparison
  const comparison = useMemo(() => {
    if (!compareBranches[0] || !compareBranches[1] || compareBranches[0] === compareBranches[1])
      return null;
    const c1 = commits.filter((c) => c.branch === compareBranches[0]);
    const c2 = commits.filter((c) => c.branch === compareBranches[1]);
    const c1Hashes = new Set(c1.map((c) => c.hash));
    const c2Hashes = new Set(c2.map((c) => c.hash));
    return {
      uniqueLeft: c1.filter((c) => !c2Hashes.has(c.hash)),
      uniqueRight: c2.filter((c) => !c1Hashes.has(c.hash)),
    };
  }, [compareBranches, commits]);

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
          Branches
        </span>
        <span className="text-[12px] mt-1 block" style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}>
          {loading ? "Loading..." : `${branches.length} branches in repository`}
        </span>
      </div>

      {/* Branch cards */}
      <div className="flex flex-col gap-2">
        {branches.map((branch) => {
          const color = branchColor(branch);
          return (
            <div
              key={branch.name}
              className="flex items-center gap-4 px-5 py-4 rounded-[10px]"
              style={{
                backgroundColor: "#111318",
                border: `1px solid #FFFFFF0A`,
                borderLeft: branch.is_current ? `3px solid ${color}` : `1px solid #FFFFFF0A`,
              }}
            >
              {/* Icon */}
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
                style={{ backgroundColor: color + "14" }}
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <circle cx="4" cy="4" r="2" stroke={color} strokeWidth="1.4" />
                  <circle cx="4" cy="12" r="2" stroke={color} strokeWidth="1.4" />
                  <circle cx="12" cy="8" r="2" stroke={color} strokeWidth="1.4" />
                  <line x1="4" y1="6" x2="4" y2="10" stroke={color} strokeWidth="1.4" />
                  <path d="M4 6 C 4 8 8 8 10 8" stroke={color} strokeWidth="1.4" fill="none" />
                </svg>
              </div>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2.5">
                  <span
                    className="text-[13px] font-medium truncate"
                    style={{
                      color: "#ECECEE",
                      fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                    }}
                  >
                    {branch.name}
                  </span>
                  {branch.is_current && (
                    <span
                      className="text-[10px] uppercase font-medium px-2 py-0.5 rounded-full"
                      style={{
                        backgroundColor: "#4ADE8018",
                        color: "#4ADE80",
                        fontFamily: "'Inter', sans-serif",
                        letterSpacing: "0.04em",
                      }}
                    >
                      current
                    </span>
                  )}
                  {/* Type badge */}
                  {branch.name.startsWith("retry/") && (
                    <span
                      className="text-[10px] uppercase font-medium px-2 py-0.5 rounded-full"
                      style={{ backgroundColor: "#E8A44A18", color: "#E8A44A", fontFamily: "'Inter', sans-serif", letterSpacing: "0.04em" }}
                    >
                      retry
                    </span>
                  )}
                  {(branch.name.startsWith("feature/") || branch.name.startsWith("experiment/")) && (
                    <span
                      className="text-[10px] uppercase font-medium px-2 py-0.5 rounded-full"
                      style={{ backgroundColor: "#5B8DEF18", color: "#5B8DEF", fontFamily: "'Inter', sans-serif", letterSpacing: "0.04em" }}
                    >
                      feature
                    </span>
                  )}
                  {branch.name.startsWith("rollback/") && (
                    <span
                      className="text-[10px] uppercase font-medium px-2 py-0.5 rounded-full"
                      style={{ backgroundColor: "#E85D5D18", color: "#E85D5D", fontFamily: "'Inter', sans-serif", letterSpacing: "0.04em" }}
                    >
                      rollback
                    </span>
                  )}
                </div>
                <span className="text-[11px] mt-1 block" style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif" }}>
                  HEAD at{" "}
                  <span style={{ color: "#5B8DEF", fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)" }}>
                    {truncateHash(branch.hash)}
                  </span>
                </span>
              </div>

              {/* Mini graph indicator */}
              <div className="flex items-center gap-1 shrink-0">
                <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
                <div className="rounded" style={{ width: "24px", height: "2px", backgroundColor: color, opacity: 0.4 }} />
                <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color, opacity: 0.4 }} />
              </div>
            </div>
          );
        })}
      </div>

      {/* SVG Branch Graph */}
      <div
        className="rounded-[10px] p-5"
        style={{ backgroundColor: "#111318", border: "1px solid #FFFFFF0A" }}
      >
        <span
          className="text-[11px] uppercase block mb-3"
          style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif", letterSpacing: "0.06em", fontWeight: 500 }}
        >
          Branch Graph
        </span>
        <BranchGraph branches={branches} commits={commits} />
      </div>

      {/* Branch Comparison */}
      <div
        className="rounded-[10px] p-5"
        style={{ backgroundColor: "#111318", border: "1px solid #FFFFFF0A" }}
      >
        <span
          className="text-[11px] uppercase block mb-3"
          style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif", letterSpacing: "0.06em", fontWeight: 500 }}
        >
          Compare Branches
        </span>
        <div className="flex items-center gap-3 mb-4">
          <select
            value={compareBranches[0]}
            onChange={(e) => setCompareBranches([e.target.value, compareBranches[1]])}
            className="text-[12px] py-1.5 px-3 rounded-[6px] outline-none"
            style={{
              backgroundColor: "#FFFFFF08",
              border: "1px solid #FFFFFF0A",
              color: "#ECECEE",
              fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
            }}
          >
            <option value="">Select branch…</option>
            {branches.map((b) => (
              <option key={b.name} value={b.name}>{b.name}</option>
            ))}
          </select>
          <span className="text-[12px]" style={{ color: "#4E5060" }}>vs</span>
          <select
            value={compareBranches[1]}
            onChange={(e) => setCompareBranches([compareBranches[0], e.target.value])}
            className="text-[12px] py-1.5 px-3 rounded-[6px] outline-none"
            style={{
              backgroundColor: "#FFFFFF08",
              border: "1px solid #FFFFFF0A",
              color: "#ECECEE",
              fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
            }}
          >
            <option value="">Select branch…</option>
            {branches.map((b) => (
              <option key={b.name} value={b.name}>{b.name}</option>
            ))}
          </select>
        </div>

        {comparison && (
          <div className="flex gap-3">
            {/* Left branch unique */}
            <div className="flex-1">
              <span className="text-[11px] block mb-2" style={{ color: "#A0A0AA", fontFamily: "'Inter', sans-serif" }}>
                Only in <span style={{ color: "#5B8DEF", fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)" }}>{compareBranches[0]}</span>
              </span>
              <div className="flex flex-col gap-1">
                {comparison.uniqueLeft.length === 0 ? (
                  <span className="text-[11px]" style={{ color: "#4E5060" }}>No unique commits</span>
                ) : (
                  comparison.uniqueLeft.map((c) => (
                    <div
                      key={c.hash}
                      className="flex items-center gap-2 px-3 py-1.5 rounded"
                      style={{ backgroundColor: "#FFFFFF05" }}
                    >
                      <span className="text-[11px]" style={{ color: "#5B8DEF", fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)" }}>
                        {truncateHash(c.hash)}
                      </span>
                      <span className="text-[11px] truncate" style={{ color: "#A0A0AA", fontFamily: "'Inter', sans-serif" }}>
                        {c.message}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
            {/* Right branch unique */}
            <div className="flex-1">
              <span className="text-[11px] block mb-2" style={{ color: "#A0A0AA", fontFamily: "'Inter', sans-serif" }}>
                Only in <span style={{ color: "#5B8DEF", fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)" }}>{compareBranches[1]}</span>
              </span>
              <div className="flex flex-col gap-1">
                {comparison.uniqueRight.length === 0 ? (
                  <span className="text-[11px]" style={{ color: "#4E5060" }}>No unique commits</span>
                ) : (
                  comparison.uniqueRight.map((c) => (
                    <div
                      key={c.hash}
                      className="flex items-center gap-2 px-3 py-1.5 rounded"
                      style={{ backgroundColor: "#FFFFFF05" }}
                    >
                      <span className="text-[11px]" style={{ color: "#5B8DEF", fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)" }}>
                        {truncateHash(c.hash)}
                      </span>
                      <span className="text-[11px] truncate" style={{ color: "#A0A0AA", fontFamily: "'Inter', sans-serif" }}>
                        {c.message}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
