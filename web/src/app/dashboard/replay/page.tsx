"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getDemoReplayTimeline, USE_DEMO_DATA } from "@/lib/api";
import type { ReplayStep } from "@/lib/api";
import { truncateHash, formatTimestamp, actionTypeColor } from "@/lib/utils";

// ---------------------------------------------------------------------------
// JSON syntax highlighter (inline, no deps)
// ---------------------------------------------------------------------------
const TOKEN_COLORS: Record<string, string> = {
  key: "#5B8DEF",
  string: "#4ADE80",
  number: "#E8A44A",
  boolean: "#E85D5D",
  null: "#6E6E76",
  brace: "#4E5060",
  comma: "#4E5060",
};

function highlightJson(obj: unknown, indent = 0): React.ReactNode[] {
  const pad = "  ".repeat(indent);
  const nodes: React.ReactNode[] = [];
  let key = 0;

  function push(text: string, color: string) {
    nodes.push(
      <span key={key++} style={{ color }}>
        {text}
      </span>
    );
  }

  function render(value: unknown, depth: number) {
    const p = "  ".repeat(depth);
    if (value === null) {
      push("null", TOKEN_COLORS.null);
    } else if (typeof value === "boolean") {
      push(String(value), TOKEN_COLORS.boolean);
    } else if (typeof value === "number") {
      push(String(value), TOKEN_COLORS.number);
    } else if (typeof value === "string") {
      push(`"${value}"`, TOKEN_COLORS.string);
    } else if (Array.isArray(value)) {
      if (value.length === 0) {
        push("[]", TOKEN_COLORS.brace);
      } else {
        push("[\n", TOKEN_COLORS.brace);
        value.forEach((item, i) => {
          push("  ".repeat(depth + 1), TOKEN_COLORS.brace);
          render(item, depth + 1);
          if (i < value.length - 1) push(",", TOKEN_COLORS.comma);
          push("\n", TOKEN_COLORS.brace);
        });
        push(p + "]", TOKEN_COLORS.brace);
      }
    } else if (typeof value === "object") {
      const entries = Object.entries(value as Record<string, unknown>);
      if (entries.length === 0) {
        push("{}", TOKEN_COLORS.brace);
      } else {
        push("{\n", TOKEN_COLORS.brace);
        entries.forEach(([k, v], i) => {
          push("  ".repeat(depth + 1), TOKEN_COLORS.brace);
          push(`"${k}"`, TOKEN_COLORS.key);
          push(": ", TOKEN_COLORS.brace);
          render(v, depth + 1);
          if (i < entries.length - 1) push(",", TOKEN_COLORS.comma);
          push("\n", TOKEN_COLORS.brace);
        });
        push(p + "}", TOKEN_COLORS.brace);
      }
    }
  }

  render(obj, indent);
  return nodes;
}

// ---------------------------------------------------------------------------
// Diff overlay: compute changed keys between two states
// ---------------------------------------------------------------------------
function getChangedPaths(
  prev: Record<string, unknown>,
  curr: Record<string, unknown>,
  prefix = ""
): Set<string> {
  const changed = new Set<string>();
  const allKeys = new Set([...Object.keys(prev), ...Object.keys(curr)]);
  for (const k of allKeys) {
    const path = prefix ? `${prefix}.${k}` : k;
    const pv = prev[k];
    const cv = curr[k];
    if (JSON.stringify(pv) !== JSON.stringify(cv)) {
      changed.add(path);
      if (
        pv && cv &&
        typeof pv === "object" && typeof cv === "object" &&
        !Array.isArray(pv) && !Array.isArray(cv)
      ) {
        for (const cp of getChangedPaths(
          pv as Record<string, unknown>,
          cv as Record<string, unknown>,
          path
        )) {
          changed.add(cp);
        }
      }
    }
  }
  return changed;
}

// ---------------------------------------------------------------------------
// Speed options
// ---------------------------------------------------------------------------
const SPEEDS = [0.5, 1, 2, 5];

// ---------------------------------------------------------------------------
// Main Replay Page
// ---------------------------------------------------------------------------
export default function ReplayPage() {
  const [timeline, setTimeline] = useState<ReplayStep[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [showDiff, setShowDiff] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (USE_DEMO_DATA) {
      setTimeline(getDemoReplayTimeline());
    }
  }, []);

  const currentStep = timeline[currentIdx] ?? null;
  const prevStep = currentIdx > 0 ? timeline[currentIdx - 1] : null;

  const changedPaths = useMemo(() => {
    if (!showDiff || !prevStep || !currentStep) return new Set<string>();
    return getChangedPaths(
      prevStep.state as Record<string, unknown>,
      currentStep.state as Record<string, unknown>
    );
  }, [showDiff, prevStep, currentStep]);

  // Playback
  const tick = useCallback(() => {
    setCurrentIdx((prev) => {
      if (prev >= timeline.length - 1) {
        setPlaying(false);
        return prev;
      }
      return prev + 1;
    });
  }, [timeline.length]);

  useEffect(() => {
    if (playing) {
      intervalRef.current = setInterval(tick, 1500 / speed);
    } else if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [playing, speed, tick]);

  if (!timeline.length) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-[13px]" style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif" }}>
          Loading replay data…
        </span>
      </div>
    );
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
            State Replay
          </span>
          <span className="text-[12px] mt-1 block" style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}>
            Step through agent state history
          </span>
        </div>
        {/* Diff toggle */}
        <button
          onClick={() => setShowDiff(!showDiff)}
          className="flex items-center gap-1.5 py-1.5 px-3 rounded-[6px] text-[12px] font-medium"
          style={{
            backgroundColor: showDiff ? "#E8A44A20" : "#FFFFFF08",
            color: showDiff ? "#E8A44A" : "#6E6E76",
            border: `1px solid ${showDiff ? "#E8A44A40" : "#FFFFFF0F"}`,
            fontFamily: "'Inter', sans-serif",
          }}
        >
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M2 4h8M2 6h5M2 8h8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
          Diff Overlay
        </button>
      </div>

      {/* Main area */}
      <div className="flex gap-3 flex-1 min-h-0">
        {/* JSON Viewer */}
        <div
          className="flex-1 rounded-[10px] overflow-hidden flex flex-col"
          style={{ backgroundColor: "#0D0E12", border: "1px solid #FFFFFF0A" }}
        >
          {/* Viewer header */}
          <div
            className="flex items-center justify-between px-4 py-2 shrink-0"
            style={{ borderBottom: "1px solid #FFFFFF08" }}
          >
            <span className="text-[11px]" style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif" }}>
              State at step {currentIdx + 1} of {timeline.length}
            </span>
            {showDiff && changedPaths.size > 0 && (
              <span className="text-[10px]" style={{ color: "#E8A44A", fontFamily: "'Inter', sans-serif" }}>
                {changedPaths.size} field{changedPaths.size !== 1 ? "s" : ""} changed
              </span>
            )}
          </div>

          {/* JSON content */}
          <div className="flex-1 overflow-auto p-4">
            <pre
              className="text-[11px]"
              style={{
                fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                lineHeight: "1.7",
              }}
            >
              {currentStep && highlightJson(currentStep.state)}
            </pre>
          </div>
        </div>

        {/* Commit metadata sidebar */}
        <div
          className="shrink-0 rounded-[10px] flex flex-col gap-4 p-4 overflow-auto"
          style={{
            width: "280px",
            backgroundColor: "#111318",
            border: "1px solid #FFFFFF0A",
          }}
        >
          {currentStep && (
            <>
              {/* Step counter */}
              <div className="flex items-center justify-between">
                <span
                  className="text-[10px] uppercase"
                  style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif", letterSpacing: "0.06em" }}
                >
                  Step
                </span>
                <span
                  className="text-[20px] font-bold"
                  style={{
                    color: "#ECECEE",
                    fontFamily: "var(--font-display, 'Space Grotesk', sans-serif)",
                  }}
                >
                  {currentIdx + 1}
                  <span className="text-[12px] font-normal" style={{ color: "#4E5060" }}>
                    {" "}/ {timeline.length}
                  </span>
                </span>
              </div>

              <div style={{ height: "1px", backgroundColor: "#FFFFFF0A" }} />

              {/* Hash */}
              <MetaRow label="Commit">
                <span style={{ color: "#5B8DEF", fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)" }}>
                  {truncateHash(currentStep.commit.hash)}
                </span>
              </MetaRow>

              {/* Message */}
              <MetaRow label="Message">
                <span style={{ color: "#ECECEE" }}>{currentStep.commit.message}</span>
              </MetaRow>

              {/* Author */}
              <MetaRow label="Author">
                <span style={{ color: "#A0A0AA" }}>{currentStep.commit.author}</span>
              </MetaRow>

              {/* Action Type */}
              <MetaRow label="Action">
                <span
                  className="text-[10px] uppercase font-medium px-2 py-0.5 rounded-full"
                  style={{
                    backgroundColor: actionTypeColor(currentStep.commit.action_type) + "18",
                    color: actionTypeColor(currentStep.commit.action_type),
                    letterSpacing: "0.03em",
                  }}
                >
                  {currentStep.commit.action_type.replace("_", " ")}
                </span>
              </MetaRow>

              {/* Timestamp */}
              <MetaRow label="Time">
                <span style={{ color: "#6E6E76", fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)" }}>
                  {formatTimestamp(currentStep.commit.timestamp)}
                </span>
              </MetaRow>

              {/* Branch */}
              {currentStep.commit.branch && (
                <MetaRow label="Branch">
                  <span className="flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: "#4ADE80" }} />
                    <span style={{ color: "#4ADE80", fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)" }}>
                      {currentStep.commit.branch}
                    </span>
                  </span>
                </MetaRow>
              )}

              {/* Diff summary */}
              {showDiff && changedPaths.size > 0 && (
                <>
                  <div style={{ height: "1px", backgroundColor: "#FFFFFF0A" }} />
                  <div>
                    <span
                      className="text-[10px] uppercase block mb-2"
                      style={{ color: "#E8A44A", fontFamily: "'Inter', sans-serif", letterSpacing: "0.06em" }}
                    >
                      Changed Fields
                    </span>
                    <div className="flex flex-col gap-1">
                      {Array.from(changedPaths).slice(0, 8).map((path) => (
                        <span
                          key={path}
                          className="text-[10px] px-2 py-0.5 rounded"
                          style={{
                            backgroundColor: "#E8A44A10",
                            color: "#E8A44A",
                            fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                          }}
                        >
                          {path}
                        </span>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>

      {/* Timeline scrubber + controls */}
      <div
        className="shrink-0 rounded-[10px] p-4 flex flex-col gap-3"
        style={{ backgroundColor: "#111318", border: "1px solid #FFFFFF0A" }}
      >
        {/* Timeline track */}
        <div className="relative flex items-center h-6">
          {/* Background track */}
          <div
            className="absolute inset-x-0 h-1 rounded-full"
            style={{ backgroundColor: "#FFFFFF0A", top: "50%", transform: "translateY(-50%)" }}
          />
          {/* Progress fill */}
          <div
            className="absolute h-1 rounded-full"
            style={{
              backgroundColor: "#5B8DEF",
              width: `${timeline.length > 1 ? (currentIdx / (timeline.length - 1)) * 100 : 0}%`,
              top: "50%",
              transform: "translateY(-50%)",
              left: 0,
            }}
          />
          {/* Commit dots */}
          {timeline.map((step, i) => {
            const pct = timeline.length > 1 ? (i / (timeline.length - 1)) * 100 : 50;
            const isActive = i === currentIdx;
            return (
              <button
                key={step.commit.hash}
                onClick={() => setCurrentIdx(i)}
                className="absolute rounded-full transition-all"
                style={{
                  left: `${pct}%`,
                  top: "50%",
                  transform: "translate(-50%, -50%)",
                  width: isActive ? "12px" : "8px",
                  height: isActive ? "12px" : "8px",
                  backgroundColor: i <= currentIdx ? "#5B8DEF" : "#FFFFFF14",
                  border: isActive ? "2px solid #ECECEE" : "none",
                  zIndex: isActive ? 2 : 1,
                }}
                title={`${truncateHash(step.commit.hash)}: ${step.commit.message}`}
              />
            );
          })}
        </div>

        {/* Controls row */}
        <div className="flex items-center justify-between">
          {/* Playback controls */}
          <div className="flex items-center gap-1">
            {/* Skip to start */}
            <ControlButton
              onClick={() => { setCurrentIdx(0); setPlaying(false); }}
              title="Skip to start"
            >
              <path d="M3 3v6M5 6l4-3v6L5 6z" fill="currentColor" />
            </ControlButton>

            {/* Step back */}
            <ControlButton
              onClick={() => { setCurrentIdx((p) => Math.max(0, p - 1)); setPlaying(false); }}
              title="Step back"
            >
              <path d="M6 3L3 6l3 3V3z" fill="currentColor" />
              <rect x="7" y="3" width="2" height="6" fill="currentColor" />
            </ControlButton>

            {/* Play / Pause */}
            <button
              onClick={() => setPlaying(!playing)}
              className="w-8 h-8 rounded-lg flex items-center justify-center"
              style={{ backgroundColor: "#5B8DEF", color: "#FFFFFF" }}
              title={playing ? "Pause" : "Play"}
            >
              <svg width="14" height="14" viewBox="0 0 12 12" fill="none">
                {playing ? (
                  <>
                    <rect x="2.5" y="2" width="2.5" height="8" rx="0.5" fill="currentColor" />
                    <rect x="7" y="2" width="2.5" height="8" rx="0.5" fill="currentColor" />
                  </>
                ) : (
                  <path d="M3 1.5L10 6L3 10.5V1.5Z" fill="currentColor" />
                )}
              </svg>
            </button>

            {/* Step forward */}
            <ControlButton
              onClick={() => { setCurrentIdx((p) => Math.min(timeline.length - 1, p + 1)); setPlaying(false); }}
              title="Step forward"
            >
              <path d="M6 3l3 3-3 3V3z" fill="currentColor" />
              <rect x="3" y="3" width="2" height="6" fill="currentColor" />
            </ControlButton>

            {/* Skip to end */}
            <ControlButton
              onClick={() => { setCurrentIdx(timeline.length - 1); setPlaying(false); }}
              title="Skip to end"
            >
              <path d="M9 3v6M3 3l4 3-4 3V3z" fill="currentColor" />
            </ControlButton>
          </div>

          {/* Speed selector */}
          <div className="flex items-center gap-0.5">
            {SPEEDS.map((s) => (
              <button
                key={s}
                onClick={() => setSpeed(s)}
                className="px-2.5 py-1 rounded text-[11px] font-medium"
                style={{
                  backgroundColor: speed === s ? "#5B8DEF20" : "transparent",
                  color: speed === s ? "#5B8DEF" : "#4E5060",
                  fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                }}
              >
                {s}x
              </button>
            ))}
          </div>

          {/* Current time label */}
          {currentStep && (
            <span
              className="text-[11px]"
              style={{ color: "#4E5060", fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)" }}
            >
              {formatTimestamp(currentStep.commit.timestamp)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

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

function ControlButton({
  onClick,
  title,
  children,
}: {
  onClick: () => void;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="w-7 h-7 rounded-lg flex items-center justify-center transition-colors"
      style={{ color: "#6E6E76", backgroundColor: "transparent" }}
      onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "#FFFFFF0A")}
      onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
    >
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        {children}
      </svg>
    </button>
  );
}
