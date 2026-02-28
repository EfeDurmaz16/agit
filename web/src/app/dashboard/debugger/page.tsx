"use client";

import { useState } from "react";

// ---------------------------------------------------------------------------
// Demo data
// ---------------------------------------------------------------------------
const DEMO_BISECT = {
  status: "in_progress" as "not_started" | "in_progress" | "completed",
  goodCommit: "dd22ee33",
  badCommit: "6677889900112233",
  currentCommit: "3b82f6a0",
  step: 3,
  totalSteps: 7,
};

type ActionType =
  | "TOOL_CALL"
  | "STATE_WRITE"
  | "POLICY_CHECK"
  | "MERGE"
  | "BRANCH"
  | "REVERT";

interface GraphNode {
  id: string;
  hash: string;
  message: string;
  actionType: ActionType;
  x: number;
  y: number;
}

interface GraphEdge {
  from: string;
  to: string;
  label: string;
  type: "DirectParent" | "StateDependent";
}

const GRAPH_NODES: GraphNode[] = [
  { id: "n1", hash: "a1b2c3d4", message: "init: bootstrap agent state", actionType: "STATE_WRITE", x: 80, y: 180 },
  { id: "n2", hash: "e5f6a7b8", message: "feat: add compliance policy check", actionType: "POLICY_CHECK", x: 220, y: 180 },
  { id: "n3", hash: "c9d0e1f2", message: "tool: invoke risk-assessor", actionType: "TOOL_CALL", x: 360, y: 100 },
  { id: "n4", hash: "33445566", message: "tool: invoke kyc-verifier", actionType: "TOOL_CALL", x: 360, y: 260 },
  { id: "n5", hash: "3b82f6a0", message: "merge: combine assessment results", actionType: "MERGE", x: 500, y: 180 },
  { id: "n6", hash: "dd22ee33", message: "write: persist final decision", actionType: "STATE_WRITE", x: 640, y: 180 },
];

const GRAPH_EDGES: GraphEdge[] = [
  { from: "n1", to: "n2", label: "DirectParent", type: "DirectParent" },
  { from: "n2", to: "n3", label: "DirectParent", type: "DirectParent" },
  { from: "n2", to: "n4", label: "DirectParent", type: "DirectParent" },
  { from: "n3", to: "n5", label: "StateDependent", type: "StateDependent" },
  { from: "n4", to: "n5", label: "StateDependent", type: "StateDependent" },
  { from: "n5", to: "n6", label: "DirectParent", type: "DirectParent" },
];

const ROOT_CAUSE = {
  hash: "c9d0e1f2",
  message: "tool: invoke risk-assessor",
  actionType: "TOOL_CALL" as ActionType,
  author: "portfolio-optimizer",
  timestamp: "2024-01-15T14:23:07Z",
  reason: "State mutation in risk-assessor output was not sanitized before propagation to merge node, causing downstream decision corruption.",
  criticalPath: [
    { hash: "c9d0e1f2", label: "Root Cause", color: "#E85D5D" },
    { hash: "3b82f6a0", label: "Propagation", color: "#E8A44A" },
    { hash: "dd22ee33", label: "Symptom", color: "#5B8DEF" },
    { hash: "6677889900112233", label: "Failure", color: "#E85D5D" },
  ],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function actionTypeColor(type: ActionType): string {
  switch (type) {
    case "TOOL_CALL": return "#5B8DEF";
    case "STATE_WRITE": return "#4ADE80";
    case "POLICY_CHECK": return "#E8A44A";
    case "MERGE": return "#A78BFA";
    case "BRANCH": return "#38BDF8";
    case "REVERT": return "#E85D5D";
    default: return "#6E6E76";
  }
}

function shortHash(hash: string): string {
  return hash.slice(0, 7);
}

function formatTimestamp(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleString("en-US", {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
    hour12: false,
  });
}

// ---------------------------------------------------------------------------
// Arrow helper: compute points for edge arrow between two nodes
// ---------------------------------------------------------------------------
function computeEdge(
  from: GraphNode,
  to: GraphNode,
  nodeRadius = 22
): { x1: number; y1: number; x2: number; y2: number; mx: number; my: number } {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const dist = Math.sqrt(dx * dx + dy * dy);
  const ux = dx / dist;
  const uy = dy / dist;
  return {
    x1: from.x + ux * nodeRadius,
    y1: from.y + uy * nodeRadius,
    x2: to.x - ux * (nodeRadius + 6),
    y2: to.y - uy * (nodeRadius + 6),
    mx: (from.x + to.x) / 2,
    my: (from.y + to.y) / 2,
  };
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------
function MetaRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span
        className="text-[10px] uppercase"
        style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif", letterSpacing: "0.06em" }}
      >
        {label}
      </span>
      <span className="text-[12px]" style={{ fontFamily: "'Inter', sans-serif" }}>
        {children}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------
export default function DebuggerPage() {
  const [goodCommit, setGoodCommit] = useState(DEMO_BISECT.goodCommit);
  const [badCommit, setBadCommit] = useState(DEMO_BISECT.badCommit);
  const [bisectStatus] = useState(DEMO_BISECT.status);
  const [bisectStep] = useState(DEMO_BISECT.step);
  const [bisectTotal] = useState(DEMO_BISECT.totalSteps);
  const [currentCommit] = useState(DEMO_BISECT.currentCommit);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  const bisectProgress = bisectTotal > 0 ? (bisectStep / bisectTotal) * 100 : 0;

  const statusLabel =
    bisectStatus === "not_started"
      ? "Not Started"
      : bisectStatus === "in_progress"
      ? `In Progress (step ${bisectStep}/${bisectTotal})`
      : "Completed";

  const statusColor =
    bisectStatus === "not_started"
      ? "#6E6E76"
      : bisectStatus === "in_progress"
      ? "#E8A44A"
      : "#4ADE80";

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* ------------------------------------------------------------------ */}
      {/* Header                                                              */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex items-center justify-between shrink-0">
        <div>
          <span
            className="text-[18px] font-semibold block"
            style={{
              color: "#ECECEE",
              fontFamily: "var(--font-display, 'Space Grotesk', sans-serif)",
              lineHeight: "22px",
            }}
          >
            Time-Travel Debugger
          </span>
          <span
            className="text-[12px] mt-1 block"
            style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}
          >
            Bisect commits and trace causal dependencies
          </span>
        </div>
        <button
          className="flex items-center gap-1.5 py-1.5 px-3 rounded-[6px] text-[12px] font-medium"
          style={{
            backgroundColor: "#5B8DEF14",
            color: "#5B8DEF",
            border: "1px solid #5B8DEF40",
            fontFamily: "'Inter', sans-serif",
          }}
        >
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <circle cx="3" cy="6" r="1.5" stroke="currentColor" strokeWidth="1.2" />
            <circle cx="9" cy="3" r="1.5" stroke="currentColor" strokeWidth="1.2" />
            <circle cx="9" cy="9" r="1.5" stroke="currentColor" strokeWidth="1.2" />
            <line x1="4.4" y1="5.3" x2="7.6" y2="3.7" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
            <line x1="4.4" y1="6.7" x2="7.6" y2="8.3" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
          </svg>
          Bisect
        </button>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Bisect Panel                                                        */}
      {/* ------------------------------------------------------------------ */}
      <div
        className="shrink-0 rounded-[10px] p-5"
        style={{ backgroundColor: "#111318", border: "1px solid #FFFFFF0A" }}
      >
        {/* Panel header row */}
        <div className="flex items-center justify-between mb-4">
          <span
            className="text-[13px] font-medium"
            style={{
              color: "#ECECEE",
              fontFamily: "var(--font-display, 'Space Grotesk', sans-serif)",
            }}
          >
            Git Bisect
          </span>
          {/* Status badge */}
          <span
            className="flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1 rounded-full"
            style={{
              backgroundColor: statusColor + "18",
              color: statusColor,
              fontFamily: "'Inter', sans-serif",
              border: `1px solid ${statusColor}30`,
            }}
          >
            {bisectStatus === "in_progress" && (
              <span
                className="w-1.5 h-1.5 rounded-full animate-pulse shrink-0"
                style={{ backgroundColor: statusColor }}
              />
            )}
            {statusLabel}
          </span>
        </div>

        <div className="flex gap-4">
          {/* Left: inputs + controls */}
          <div className="flex flex-col gap-3 flex-1 min-w-0">
            {/* Commit inputs */}
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <label
                  className="text-[10px] uppercase"
                  style={{ color: "#4ADE80", fontFamily: "'Inter', sans-serif", letterSpacing: "0.06em" }}
                >
                  Good Commit
                </label>
                <div className="relative">
                  <span
                    className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[10px]"
                    style={{ color: "#4ADE80" }}
                  >
                    ✓
                  </span>
                  <input
                    type="text"
                    value={goodCommit}
                    onChange={(e) => setGoodCommit(e.target.value)}
                    className="w-full py-1.5 pl-7 pr-3 rounded-[6px] text-[12px] outline-none"
                    style={{
                      backgroundColor: "#4ADE8010",
                      border: "1px solid #4ADE8030",
                      color: "#4ADE80",
                      fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                    }}
                  />
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <label
                  className="text-[10px] uppercase"
                  style={{ color: "#E85D5D", fontFamily: "'Inter', sans-serif", letterSpacing: "0.06em" }}
                >
                  Bad Commit
                </label>
                <div className="relative">
                  <span
                    className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[10px]"
                    style={{ color: "#E85D5D" }}
                  >
                    ✗
                  </span>
                  <input
                    type="text"
                    value={badCommit}
                    onChange={(e) => setBadCommit(e.target.value)}
                    className="w-full py-1.5 pl-7 pr-3 rounded-[6px] text-[12px] outline-none"
                    style={{
                      backgroundColor: "#E85D5D10",
                      border: "1px solid #E85D5D30",
                      color: "#E85D5D",
                      fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                    }}
                  />
                </div>
              </div>
            </div>

            {/* Current commit under test */}
            <div
              className="flex items-center justify-between px-3 py-2.5 rounded-[8px]"
              style={{ backgroundColor: "#E8A44A0A", border: "1px solid #E8A44A20" }}
            >
              <div className="flex flex-col gap-0.5">
                <span
                  className="text-[10px] uppercase"
                  style={{ color: "#E8A44A", fontFamily: "'Inter', sans-serif", letterSpacing: "0.06em" }}
                >
                  Currently Testing
                </span>
                <span
                  className="text-[13px] font-medium"
                  style={{
                    color: "#ECECEE",
                    fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                  }}
                >
                  {currentCommit}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  className="py-1.5 px-3 rounded-[6px] text-[12px] font-medium"
                  style={{
                    backgroundColor: "#4ADE8018",
                    color: "#4ADE80",
                    border: "1px solid #4ADE8030",
                    fontFamily: "'Inter', sans-serif",
                  }}
                >
                  Mark Good
                </button>
                <button
                  className="py-1.5 px-3 rounded-[6px] text-[12px] font-medium"
                  style={{
                    backgroundColor: "#E85D5D18",
                    color: "#E85D5D",
                    border: "1px solid #E85D5D30",
                    fontFamily: "'Inter', sans-serif",
                  }}
                >
                  Mark Bad
                </button>
              </div>
            </div>

            {/* Progress bar */}
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <span
                  className="text-[10px]"
                  style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}
                >
                  Bisect progress
                </span>
                <span
                  className="text-[10px]"
                  style={{
                    color: "#A0A0AA",
                    fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                  }}
                >
                  {bisectStep} / {bisectTotal} steps
                </span>
              </div>
              <div
                className="h-1.5 rounded-full overflow-hidden"
                style={{ backgroundColor: "#FFFFFF0A" }}
              >
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${bisectProgress}%`,
                    background: "linear-gradient(90deg, #5B8DEF, #A78BFA)",
                  }}
                />
              </div>
              <div className="flex items-center justify-between">
                <span
                  className="text-[10px]"
                  style={{
                    color: "#4ADE80",
                    fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                  }}
                >
                  {shortHash(goodCommit)}
                </span>
                <span
                  className="text-[10px]"
                  style={{
                    color: "#E85D5D",
                    fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                  }}
                >
                  {shortHash(badCommit)}
                </span>
              </div>
            </div>
          </div>

          {/* Right: start button + stats */}
          <div className="flex flex-col gap-3 shrink-0" style={{ width: "160px" }}>
            <button
              className="w-full py-2 px-4 rounded-[8px] text-[13px] font-medium"
              style={{
                backgroundColor: "#5B8DEF",
                color: "#FFFFFF",
                fontFamily: "'Inter', sans-serif",
              }}
            >
              Start Bisect
            </button>

            <div
              className="flex flex-col gap-2.5 p-3 rounded-[8px]"
              style={{ backgroundColor: "#0C0D10", border: "1px solid #FFFFFF08" }}
            >
              <div className="flex justify-between items-center">
                <span className="text-[10px]" style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}>
                  Remaining
                </span>
                <span
                  className="text-[12px] font-medium"
                  style={{
                    color: "#ECECEE",
                    fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                  }}
                >
                  {bisectTotal - bisectStep}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-[10px]" style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}>
                  Est. commits
                </span>
                <span
                  className="text-[12px] font-medium"
                  style={{
                    color: "#ECECEE",
                    fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                  }}
                >
                  ~{Math.pow(2, bisectTotal - bisectStep)}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Bottom: Graph + Root Cause sidebar                                  */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex gap-3 flex-1 min-h-0">
        {/* Causal Graph */}
        <div
          className="flex-1 rounded-[10px] flex flex-col overflow-hidden"
          style={{ backgroundColor: "#111318", border: "1px solid #FFFFFF0A" }}
        >
          {/* Graph header */}
          <div
            className="flex items-center justify-between px-5 py-3 shrink-0"
            style={{ borderBottom: "1px solid #FFFFFF08" }}
          >
            <span
              className="text-[13px] font-medium"
              style={{
                color: "#ECECEE",
                fontFamily: "var(--font-display, 'Space Grotesk', sans-serif)",
              }}
            >
              Causal Dependency Graph
            </span>
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-1.5 text-[10px]" style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}>
                <span className="inline-block w-6 h-px" style={{ backgroundColor: "#5B8DEF" }} />
                DirectParent
              </span>
              <span className="flex items-center gap-1.5 text-[10px]" style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}>
                <span
                  className="inline-block w-6 h-px"
                  style={{ backgroundColor: "#A78BFA", borderTop: "1px dashed #A78BFA" }}
                />
                StateDependent
              </span>
            </div>
          </div>

          {/* SVG Graph */}
          <div className="flex-1 relative overflow-hidden">
            <svg
              className="w-full h-full"
              viewBox="0 0 760 360"
              preserveAspectRatio="xMidYMid meet"
            >
              <defs>
                <marker
                  id="arrow-direct"
                  markerWidth="8"
                  markerHeight="8"
                  refX="6"
                  refY="3"
                  orient="auto"
                >
                  <path d="M0,0 L0,6 L8,3 z" fill="#5B8DEF" opacity="0.7" />
                </marker>
                <marker
                  id="arrow-state"
                  markerWidth="8"
                  markerHeight="8"
                  refX="6"
                  refY="3"
                  orient="auto"
                >
                  <path d="M0,0 L0,6 L8,3 z" fill="#A78BFA" opacity="0.7" />
                </marker>
              </defs>

              {/* Edges */}
              {GRAPH_EDGES.map((edge) => {
                const fromNode = GRAPH_NODES.find((n) => n.id === edge.from)!;
                const toNode = GRAPH_NODES.find((n) => n.id === edge.to)!;
                const { x1, y1, x2, y2, mx, my } = computeEdge(fromNode, toNode);
                const isDirect = edge.type === "DirectParent";
                const color = isDirect ? "#5B8DEF" : "#A78BFA";
                const markerId = isDirect ? "arrow-direct" : "arrow-state";

                return (
                  <g key={`${edge.from}-${edge.to}`}>
                    <line
                      x1={x1}
                      y1={y1}
                      x2={x2}
                      y2={y2}
                      stroke={color}
                      strokeWidth="1.5"
                      strokeOpacity="0.5"
                      strokeDasharray={isDirect ? undefined : "4 3"}
                      markerEnd={`url(#${markerId})`}
                    />
                    <text
                      x={mx}
                      y={my - 6}
                      textAnchor="middle"
                      fontSize="8"
                      fill={color}
                      opacity="0.5"
                      fontFamily="'Inter', sans-serif"
                    >
                      {edge.label}
                    </text>
                  </g>
                );
              })}

              {/* Nodes */}
              {GRAPH_NODES.map((node) => {
                const color = actionTypeColor(node.actionType);
                const isSelected = selectedNode?.id === node.id;
                const isCurrent = node.hash === currentCommit;
                const isRoot = node.hash === ROOT_CAUSE.hash;

                return (
                  <g
                    key={node.id}
                    style={{ cursor: "pointer" }}
                    onClick={() => setSelectedNode(isSelected ? null : node)}
                  >
                    {/* Outer glow for special nodes */}
                    {(isCurrent || isRoot) && (
                      <circle
                        cx={node.x}
                        cy={node.y}
                        r={30}
                        fill="none"
                        stroke={isRoot ? "#E85D5D" : "#E8A44A"}
                        strokeWidth="1"
                        strokeOpacity="0.3"
                        strokeDasharray="3 3"
                      />
                    )}

                    {/* Main circle */}
                    <circle
                      cx={node.x}
                      cy={node.y}
                      r={22}
                      fill={color + (isSelected ? "30" : "18")}
                      stroke={isSelected ? color : color + "50"}
                      strokeWidth={isSelected ? 2 : 1.5}
                    />

                    {/* Hash label */}
                    <text
                      x={node.x}
                      y={node.y + 1}
                      textAnchor="middle"
                      dominantBaseline="middle"
                      fontSize="9"
                      fontWeight="600"
                      fill={color}
                      fontFamily="var(--font-mono, 'JetBrains Mono', monospace)"
                    >
                      {shortHash(node.hash)}
                    </text>

                    {/* Action type badge below node */}
                    <rect
                      x={node.x - 28}
                      y={node.y + 26}
                      width={56}
                      height={14}
                      rx={4}
                      fill={color + "20"}
                    />
                    <text
                      x={node.x}
                      y={node.y + 33}
                      textAnchor="middle"
                      dominantBaseline="middle"
                      fontSize="7"
                      fill={color}
                      fontFamily="'Inter', sans-serif"
                      fontWeight="500"
                    >
                      {node.actionType.replace("_", " ")}
                    </text>

                    {/* Message excerpt above */}
                    <text
                      x={node.x}
                      y={node.y - 28}
                      textAnchor="middle"
                      fontSize="8"
                      fill="#6E6E76"
                      fontFamily="'Inter', sans-serif"
                    >
                      {node.message.length > 22
                        ? node.message.slice(0, 22) + "…"
                        : node.message}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>

          {/* Selected node detail strip */}
          {selectedNode && (
            <div
              className="shrink-0 px-5 py-3 flex items-center gap-4"
              style={{ borderTop: "1px solid #FFFFFF08", backgroundColor: "#0D0E12" }}
            >
              <span
                className="text-[11px]"
                style={{
                  color: actionTypeColor(selectedNode.actionType),
                  fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                }}
              >
                {selectedNode.hash}
              </span>
              <span
                className="w-px h-3 shrink-0"
                style={{ backgroundColor: "#FFFFFF14" }}
              />
              <span
                className="text-[12px] flex-1"
                style={{ color: "#ECECEE", fontFamily: "'Inter', sans-serif" }}
              >
                {selectedNode.message}
              </span>
              <span
                className="text-[10px] uppercase px-2 py-0.5 rounded-full"
                style={{
                  backgroundColor: actionTypeColor(selectedNode.actionType) + "20",
                  color: actionTypeColor(selectedNode.actionType),
                  fontFamily: "'Inter', sans-serif",
                  letterSpacing: "0.04em",
                }}
              >
                {selectedNode.actionType.replace("_", " ")}
              </span>
              <button
                onClick={() => setSelectedNode(null)}
                className="text-[10px]"
                style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif" }}
              >
                Dismiss
              </button>
            </div>
          )}
        </div>

        {/* Root Cause Sidebar */}
        <div
          className="shrink-0 rounded-[10px] flex flex-col gap-4 p-4 overflow-auto"
          style={{
            width: "260px",
            backgroundColor: "#111318",
            border: "1px solid #FFFFFF0A",
          }}
        >
          {/* Sidebar header */}
          <div className="flex items-center gap-2">
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ backgroundColor: "#E85D5D", boxShadow: "0 0 6px #E85D5D60" }}
            />
            <span
              className="text-[13px] font-medium"
              style={{
                color: "#ECECEE",
                fontFamily: "var(--font-display, 'Space Grotesk', sans-serif)",
              }}
            >
              Root Cause Analysis
            </span>
          </div>

          <div style={{ height: "1px", backgroundColor: "#FFFFFF0A" }} />

          {/* Root cause commit card */}
          <div
            className="p-3 rounded-[8px]"
            style={{ backgroundColor: "#E85D5D0A", border: "1px solid #E85D5D20" }}
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <span
                className="text-[11px] font-medium"
                style={{
                  color: "#E85D5D",
                  fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                }}
              >
                {shortHash(ROOT_CAUSE.hash)}
              </span>
              <span
                className="text-[9px] uppercase px-1.5 py-0.5 rounded"
                style={{
                  backgroundColor: actionTypeColor(ROOT_CAUSE.actionType) + "20",
                  color: actionTypeColor(ROOT_CAUSE.actionType),
                  fontFamily: "'Inter', sans-serif",
                  letterSpacing: "0.04em",
                }}
              >
                {ROOT_CAUSE.actionType.replace("_", " ")}
              </span>
            </div>
            <p
              className="text-[11px] leading-[1.5] mb-2"
              style={{ color: "#A0A0AA", fontFamily: "'Inter', sans-serif" }}
            >
              {ROOT_CAUSE.message}
            </p>
            <div className="flex flex-col gap-1">
              <MetaRow label="Author">
                <span style={{ color: "#A0A0AA" }}>{ROOT_CAUSE.author}</span>
              </MetaRow>
              <MetaRow label="Time">
                <span style={{ color: "#6E6E76", fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)" }}>
                  {formatTimestamp(ROOT_CAUSE.timestamp)}
                </span>
              </MetaRow>
            </div>
          </div>

          {/* Reason */}
          <div className="flex flex-col gap-1.5">
            <span
              className="text-[10px] uppercase"
              style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif", letterSpacing: "0.06em" }}
            >
              Analysis
            </span>
            <p
              className="text-[11px] leading-[1.6]"
              style={{ color: "#A0A0AA", fontFamily: "'Inter', sans-serif" }}
            >
              {ROOT_CAUSE.reason}
            </p>
          </div>

          <div style={{ height: "1px", backgroundColor: "#FFFFFF0A" }} />

          {/* Critical path timeline */}
          <div className="flex flex-col gap-1.5">
            <span
              className="text-[10px] uppercase"
              style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif", letterSpacing: "0.06em" }}
            >
              Critical Path
            </span>
            <div className="flex flex-col">
              {ROOT_CAUSE.criticalPath.map((item, i) => (
                <div key={item.hash} className="flex items-stretch gap-2.5">
                  {/* Timeline line + dot */}
                  <div className="flex flex-col items-center shrink-0" style={{ width: "16px" }}>
                    <div
                      className="w-2.5 h-2.5 rounded-full shrink-0 mt-1"
                      style={{
                        backgroundColor: item.color + "30",
                        border: `1.5px solid ${item.color}`,
                      }}
                    />
                    {i < ROOT_CAUSE.criticalPath.length - 1 && (
                      <div
                        className="flex-1 w-px mt-1"
                        style={{ backgroundColor: "#FFFFFF14", minHeight: "16px" }}
                      />
                    )}
                  </div>
                  {/* Content */}
                  <div className="flex flex-col gap-0.5 pb-3">
                    <span
                      className="text-[10px] uppercase font-medium"
                      style={{
                        color: item.color,
                        fontFamily: "'Inter', sans-serif",
                        letterSpacing: "0.04em",
                      }}
                    >
                      {item.label}
                    </span>
                    <span
                      className="text-[10px]"
                      style={{
                        color: "#6E6E76",
                        fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                      }}
                    >
                      {shortHash(item.hash)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div style={{ height: "1px", backgroundColor: "#FFFFFF0A" }} />

          {/* Confidence indicator */}
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between">
              <span
                className="text-[10px] uppercase"
                style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif", letterSpacing: "0.06em" }}
              >
                Confidence
              </span>
              <span
                className="text-[11px] font-medium"
                style={{ color: "#4ADE80", fontFamily: "'Inter', sans-serif" }}
              >
                94%
              </span>
            </div>
            <div
              className="h-1 rounded-full overflow-hidden"
              style={{ backgroundColor: "#FFFFFF0A" }}
            >
              <div
                className="h-full rounded-full"
                style={{ width: "94%", backgroundColor: "#4ADE80" }}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
