"use client";

import { useEffect, useMemo, useState } from "react";
import {
  api,
  getDemoData,
  getDemoCommitState,
  getDemoDiff,
  USE_DEMO_DATA,
} from "@/lib/api";
import type { Commit } from "@/lib/api";
import { truncateHash, formatTimestamp, actionTypeColor } from "@/lib/utils";
import { DiffPanel } from "../diff/components";

// ---------------------------------------------------------------------------
// Lane assignment for DAG visualization
// ---------------------------------------------------------------------------
const LANE_COLORS = ["#5B8DEF", "#4ADE80", "#E8A44A", "#E85D5D", "#A78BFA", "#F472B6"];

interface LaneInfo {
  lane: number;
  color: string;
}

function assignLanes(commits: Commit[]): Map<string, LaneInfo> {
  const map = new Map<string, LaneInfo>();
  const activeLanes: (string | null)[] = [];

  for (const c of commits) {
    // find an existing lane that expects this commit
    let lane = activeLanes.indexOf(c.hash);
    if (lane === -1) {
      // allocate new lane
      lane = activeLanes.indexOf(null);
      if (lane === -1) {
        lane = activeLanes.length;
        activeLanes.push(null);
      }
    }
    activeLanes[lane] = null;

    const color = LANE_COLORS[lane % LANE_COLORS.length];
    map.set(c.hash, { lane, color });

    // assign parent expectations
    for (const ph of c.parent_hashes) {
      if (!activeLanes.includes(ph)) {
        // try same lane first
        if (activeLanes[lane] === null) {
          activeLanes[lane] = ph;
        } else {
          const free = activeLanes.indexOf(null);
          if (free !== -1) activeLanes[free] = ph;
          else activeLanes.push(ph);
        }
      }
    }
  }
  return map;
}

// ---------------------------------------------------------------------------
// SVG DAG Column
// ---------------------------------------------------------------------------
const ROW_H = 52;
const NODE_R = 4;
const LANE_W = 18;
const DAG_PAD = 12;

function DagColumn({ commits, lanes }: { commits: Commit[]; lanes: Map<string, LaneInfo> }) {
  const hashIndex = new Map(commits.map((c, i) => [c.hash, i]));
  const maxLane = Math.max(0, ...Array.from(lanes.values()).map((l) => l.lane));
  const svgW = DAG_PAD * 2 + (maxLane + 1) * LANE_W;
  const svgH = commits.length * ROW_H;

  const lines: React.ReactNode[] = [];
  const circles: React.ReactNode[] = [];

  commits.forEach((c, idx) => {
    const info = lanes.get(c.hash);
    if (!info) return;
    const cx = DAG_PAD + info.lane * LANE_W + LANE_W / 2;
    const cy = idx * ROW_H + ROW_H / 2;

    // draw lines to parents
    for (const ph of c.parent_hashes) {
      const pi = hashIndex.get(ph);
      if (pi === undefined) continue;
      const pInfo = lanes.get(ph);
      if (!pInfo) continue;
      const px = DAG_PAD + pInfo.lane * LANE_W + LANE_W / 2;
      const py = pi * ROW_H + ROW_H / 2;

      if (info.lane === pInfo.lane) {
        lines.push(
          <line
            key={`${c.hash}-${ph}`}
            x1={cx} y1={cy} x2={px} y2={py}
            stroke={info.color}
            strokeWidth="1.5"
            strokeOpacity="0.5"
          />
        );
      } else {
        const midY = cy + ROW_H * 0.6;
        lines.push(
          <path
            key={`${c.hash}-${ph}`}
            d={`M${cx},${cy} L${cx},${midY} Q${cx},${py - ROW_H * 0.2} ${px},${py}`}
            stroke={info.color}
            strokeWidth="1.5"
            strokeOpacity="0.4"
            fill="none"
          />
        );
      }
    }

    // node circle
    circles.push(
      <circle
        key={c.hash}
        cx={cx} cy={cy} r={NODE_R}
        fill={info.color}
        stroke="#0C0D10"
        strokeWidth="1.5"
      />
    );
  });

  return (
    <svg
      width={svgW}
      height={svgH}
      viewBox={`0 0 ${svgW} ${svgH}`}
      style={{ display: "block", flexShrink: 0 }}
    >
      {lines}
      {circles}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Action type filter pill
// ---------------------------------------------------------------------------
function FilterPill({
  label,
  active,
  color,
  onClick,
}: {
  label: string;
  active: boolean;
  color: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="px-2.5 py-1 rounded-full text-[11px] font-medium transition-colors"
      style={{
        backgroundColor: active ? color + "20" : "#FFFFFF08",
        color: active ? color : "#6E6E76",
        border: `1px solid ${active ? color + "40" : "#FFFFFF0A"}`,
        fontFamily: "'Inter', sans-serif",
      }}
    >
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function CommitsPage() {
  const [commits, setCommits] = useState<Commit[]>(
    USE_DEMO_DATA ? getDemoData().commits : []
  );
  const [expandedHash, setExpandedHash] = useState<string | null>(null);
  const [expandedState, setExpandedState] = useState<Record<string, unknown> | null>(null);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(!USE_DEMO_DATA);
  // Compare mode
  const [compareMode, setCompareMode] = useState(false);
  const [compareSelection, setCompareSelection] = useState<string[]>([]);
  const [compareDiff, setCompareDiff] = useState<ReturnType<typeof getDemoDiff> | null>(null);

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

  const actionTypes = useMemo(
    () => ["all", ...Array.from(new Set(commits.map((c) => c.action_type)))],
    [commits]
  );

  const filtered = useMemo(() => {
    let list = commits;
    if (filter !== "all") list = list.filter((c) => c.action_type === filter);
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(
        (c) =>
          c.message.toLowerCase().includes(q) ||
          c.hash.toLowerCase().includes(q) ||
          c.author.toLowerCase().includes(q)
      );
    }
    return list;
  }, [commits, filter, search]);

  const lanes = useMemo(() => assignLanes(filtered), [filtered]);

  // Expand handler — fetch state
  function handleExpand(hash: string) {
    if (expandedHash === hash) {
      setExpandedHash(null);
      setExpandedState(null);
      return;
    }
    setExpandedHash(hash);
    if (USE_DEMO_DATA) {
      setExpandedState(getDemoCommitState(hash));
    } else {
      api
        .getCommit(hash)
        .then((r) => setExpandedState(r.state))
        .catch(() => setExpandedState(null));
    }
  }

  // Compare handler
  function handleCompareToggle(hash: string) {
    setCompareSelection((prev) => {
      if (prev.includes(hash)) return prev.filter((h) => h !== hash);
      if (prev.length >= 2) return [prev[1], hash];
      return [...prev, hash];
    });
  }

  function handleCompare() {
    if (compareSelection.length !== 2) return;
    if (USE_DEMO_DATA) {
      setCompareDiff(getDemoDiff(compareSelection[0], compareSelection[1]));
    } else {
      api
        .getDiff(compareSelection[0], compareSelection[1])
        .then(setCompareDiff)
        .catch(() => setCompareDiff(null));
    }
  }

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
            Commits
          </span>
          <span className="text-[12px] mt-1 block" style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}>
            {loading ? "Loading..." : `${commits.length} commits across all branches`}
          </span>
        </div>
        <button
          onClick={() => {
            setCompareMode(!compareMode);
            setCompareSelection([]);
            setCompareDiff(null);
          }}
          className="flex items-center gap-1.5 py-1.5 px-3 rounded-[6px] text-[12px] font-medium"
          style={{
            backgroundColor: compareMode ? "#5B8DEF20" : "#FFFFFF08",
            color: compareMode ? "#5B8DEF" : "#6E6E76",
            border: `1px solid ${compareMode ? "#5B8DEF40" : "#FFFFFF0F"}`,
            fontFamily: "'Inter', sans-serif",
          }}
        >
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M2 3h8M2 6h5M2 9h8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
          Compare
        </button>
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-2 flex-wrap">
        {actionTypes.map((type) => (
          <FilterPill
            key={type}
            label={type === "all" ? "All" : type.replace("_", " ")}
            active={filter === type}
            color={type === "all" ? "#ECECEE" : actionTypeColor(type)}
            onClick={() => setFilter(type)}
          />
        ))}
        <div className="flex-1" />
        <div className="relative">
          <svg
            width="12" height="12" viewBox="0 0 12 12" fill="none"
            className="absolute left-2.5 top-1/2 -translate-y-1/2"
          >
            <circle cx="5" cy="5" r="3.5" stroke="#4E5060" strokeWidth="1.2" />
            <line x1="7.8" y1="7.8" x2="10.5" y2="10.5" stroke="#4E5060" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
          <input
            type="text"
            placeholder="Search commits..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="py-1.5 pl-8 pr-3 rounded-[6px] text-[12px] outline-none"
            style={{
              backgroundColor: "#FFFFFF08",
              border: "1px solid #FFFFFF0A",
              color: "#ECECEE",
              fontFamily: "'Inter', sans-serif",
              width: "200px",
            }}
          />
        </div>
      </div>

      {/* Compare bar */}
      {compareMode && (
        <div
          className="flex items-center gap-3 px-4 py-2.5 rounded-lg"
          style={{ backgroundColor: "#5B8DEF10", border: "1px solid #5B8DEF30" }}
        >
          <span className="text-[12px]" style={{ color: "#5B8DEF", fontFamily: "'Inter', sans-serif" }}>
            Select 2 commits to compare
          </span>
          <div className="flex-1" />
          {compareSelection.map((h) => (
            <span
              key={h}
              className="text-[11px] px-2 py-0.5 rounded"
              style={{
                backgroundColor: "#5B8DEF20",
                color: "#5B8DEF",
                fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
              }}
            >
              {truncateHash(h)}
            </span>
          ))}
          {compareSelection.length === 2 && (
            <button
              onClick={handleCompare}
              className="text-[11px] font-medium px-3 py-1 rounded-[5px]"
              style={{
                backgroundColor: "#ECECEE",
                color: "#0C0D10",
                fontFamily: "'Inter', sans-serif",
              }}
            >
              Compare
            </button>
          )}
        </div>
      )}

      {/* Inline diff result */}
      {compareDiff && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-[13px] font-medium" style={{ color: "#ECECEE", fontFamily: "'Inter', sans-serif" }}>
              Diff: {truncateHash(compareDiff.base_hash)} → {truncateHash(compareDiff.target_hash)}
            </span>
            <button
              onClick={() => setCompareDiff(null)}
              className="text-[11px] px-2 py-0.5 rounded"
              style={{ color: "#6E6E76", backgroundColor: "#FFFFFF08" }}
            >
              Close
            </button>
          </div>
          <DiffPanel diff={compareDiff} />
        </div>
      )}

      {/* Commit list with DAG */}
      <div
        className="flex rounded-[10px] overflow-hidden flex-1 min-h-0"
        style={{ backgroundColor: "#111318", border: "1px solid #FFFFFF0A" }}
      >
        {/* DAG column */}
        <div className="overflow-y-auto shrink-0" style={{ borderRight: "1px solid #FFFFFF0A" }}>
          <DagColumn commits={filtered} lanes={lanes} />
        </div>

        {/* Rows */}
        <div className="flex-1 overflow-y-auto">
          {filtered.map((commit) => {
            const isExpanded = expandedHash === commit.hash;
            const isSelected = compareSelection.includes(commit.hash);
            const laneInfo = lanes.get(commit.hash);

            return (
              <div key={commit.hash}>
                <button
                  onClick={() => {
                    if (compareMode) handleCompareToggle(commit.hash);
                    else handleExpand(commit.hash);
                  }}
                  className="w-full text-left flex items-center gap-3 px-4 transition-colors"
                  style={{
                    height: `${ROW_H}px`,
                    backgroundColor: isSelected
                      ? "#5B8DEF10"
                      : isExpanded
                      ? "#FFFFFF05"
                      : "transparent",
                    borderBottom: "1px solid #FFFFFF06",
                  }}
                >
                  {/* Compare checkbox */}
                  {compareMode && (
                    <div
                      className="w-4 h-4 rounded shrink-0 flex items-center justify-center"
                      style={{
                        border: `1.5px solid ${isSelected ? "#5B8DEF" : "#FFFFFF1A"}`,
                        backgroundColor: isSelected ? "#5B8DEF" : "transparent",
                      }}
                    >
                      {isSelected && (
                        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                          <path d="M2 5l2.5 2.5L8 3" stroke="#FFF" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      )}
                    </div>
                  )}

                  {/* Hash */}
                  <span
                    className="text-[11px] shrink-0"
                    style={{
                      color: "#5B8DEF",
                      fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                      width: "72px",
                    }}
                  >
                    {truncateHash(commit.hash)}
                  </span>

                  {/* Message */}
                  <span
                    className="text-[12px] flex-1 truncate"
                    style={{ color: "#ECECEE", fontFamily: "'Inter', sans-serif" }}
                  >
                    {commit.message}
                  </span>

                  {/* Action badge */}
                  <span
                    className="text-[10px] uppercase font-medium px-2 py-0.5 rounded-full shrink-0"
                    style={{
                      backgroundColor: actionTypeColor(commit.action_type) + "18",
                      color: actionTypeColor(commit.action_type),
                      fontFamily: "'Inter', sans-serif",
                      letterSpacing: "0.03em",
                    }}
                  >
                    {commit.action_type.replace("_", " ")}
                  </span>

                  {/* Author */}
                  <span
                    className="text-[11px] shrink-0"
                    style={{
                      color: "#4E5060",
                      fontFamily: "'Inter', sans-serif",
                      width: "100px",
                      textAlign: "right",
                    }}
                  >
                    {commit.author}
                  </span>

                  {/* Time */}
                  <span
                    className="text-[11px] shrink-0"
                    style={{
                      color: "#4E5060",
                      fontFamily: "'Inter', sans-serif",
                      width: "80px",
                      textAlign: "right",
                    }}
                  >
                    {formatTimestamp(commit.timestamp).split(",").pop()?.trim()}
                  </span>

                  {/* Chevron */}
                  {!compareMode && (
                    <svg
                      width="12" height="12" viewBox="0 0 12 12" fill="none"
                      className="shrink-0 transition-transform"
                      style={{
                        color: "#4E5060",
                        transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)",
                      }}
                    >
                      <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </button>

                {/* Expanded detail */}
                {isExpanded && !compareMode && (
                  <div
                    className="px-5 py-4"
                    style={{
                      backgroundColor: "#0D0E12",
                      borderBottom: "1px solid #FFFFFF08",
                    }}
                  >
                    <div className="flex flex-col gap-3">
                      {/* Detail rows */}
                      <div className="flex gap-8">
                        <DetailItem label="Full Hash" mono>{commit.hash}</DetailItem>
                        <DetailItem label="Author">{commit.author}</DetailItem>
                        <DetailItem label="Timestamp">{formatTimestamp(commit.timestamp)}</DetailItem>
                      </div>
                      <div className="flex gap-8">
                        <DetailItem label="Action Type">
                          <span style={{ color: actionTypeColor(commit.action_type) }}>
                            {commit.action_type}
                          </span>
                        </DetailItem>
                        <DetailItem label="Parents" mono>
                          {commit.parent_hashes.length > 0 ? (
                            <span className="flex gap-2">
                              {commit.parent_hashes.map((ph) => (
                                <button
                                  key={ph}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleExpand(ph);
                                  }}
                                  className="hover:underline"
                                  style={{ color: "#5B8DEF" }}
                                >
                                  {truncateHash(ph)}
                                </button>
                              ))}
                            </span>
                          ) : (
                            <span style={{ color: "#4E5060" }}>root</span>
                          )}
                        </DetailItem>
                        {laneInfo && (
                          <DetailItem label="Branch">
                            <span className="flex items-center gap-1.5">
                              <span
                                className="w-2 h-2 rounded-full shrink-0"
                                style={{ backgroundColor: laneInfo.color }}
                              />
                              <span style={{ color: laneInfo.color }}>
                                {commit.branch || "—"}
                              </span>
                            </span>
                          </DetailItem>
                        )}
                      </div>

                      {/* State JSON */}
                      {expandedState && (
                        <div className="mt-1">
                          <span
                            className="text-[10px] uppercase block mb-2"
                            style={{
                              color: "#4E5060",
                              fontFamily: "'Inter', sans-serif",
                              letterSpacing: "0.06em",
                            }}
                          >
                            State
                          </span>
                          <pre
                            className="text-[11px] p-4 rounded-lg overflow-auto"
                            style={{
                              backgroundColor: "#0C0D10",
                              border: "1px solid #FFFFFF0A",
                              color: "#A0A0AA",
                              fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                              maxHeight: "240px",
                              lineHeight: "1.6",
                            }}
                          >
                            {JSON.stringify(expandedState, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function DetailItem({
  label,
  children,
  mono,
}: {
  label: string;
  children: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span
        className="text-[10px] uppercase"
        style={{
          color: "#4E5060",
          fontFamily: "'Inter', sans-serif",
          letterSpacing: "0.06em",
        }}
      >
        {label}
      </span>
      <span
        className="text-[12px]"
        style={{
          color: "#A0A0AA",
          fontFamily: mono
            ? "var(--font-mono, 'JetBrains Mono', monospace)"
            : "'Inter', sans-serif",
        }}
      >
        {children}
      </span>
    </div>
  );
}
