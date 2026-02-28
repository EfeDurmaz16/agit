"use client";

import type { DiffEntry, StateDiff } from "@/lib/api";

const changeColors: Record<string, { bg: string; text: string; label: string }> = {
  added: { bg: "#4ADE8018", text: "#4ADE80", label: "added" },
  removed: { bg: "#E85D5D18", text: "#E85D5D", label: "removed" },
  changed: { bg: "#5B8DEF18", text: "#5B8DEF", label: "changed" },
};

export function DiffSummaryBar({ entries }: { entries: DiffEntry[] }) {
  const added = entries.filter((e) => e.change_type === "added").length;
  const removed = entries.filter((e) => e.change_type === "removed").length;
  const changed = entries.filter((e) => e.change_type === "changed").length;

  return (
    <div
      className="flex items-center gap-4 px-4 py-2.5 rounded-lg"
      style={{ backgroundColor: "#0D0E12", border: "1px solid #FFFFFF0A" }}
    >
      <span
        className="text-[12px]"
        style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}
      >
        {entries.length} changes
      </span>
      <div
        className="shrink-0"
        style={{ width: "1px", height: "14px", backgroundColor: "#FFFFFF0F" }}
      />
      {added > 0 && (
        <span className="text-[12px]" style={{ color: "#4ADE80", fontFamily: "'Inter', sans-serif" }}>
          +{added} added
        </span>
      )}
      {removed > 0 && (
        <span className="text-[12px]" style={{ color: "#E85D5D", fontFamily: "'Inter', sans-serif" }}>
          -{removed} removed
        </span>
      )}
      {changed > 0 && (
        <span className="text-[12px]" style={{ color: "#5B8DEF", fontFamily: "'Inter', sans-serif" }}>
          ~{changed} changed
        </span>
      )}
    </div>
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (typeof value === "string") return `"${value}"`;
  return JSON.stringify(value, null, 2);
}

export function DiffEntryCard({
  entry,
  defaultOpen = false,
}: {
  entry: DiffEntry;
  defaultOpen?: boolean;
}) {
  const colors = changeColors[entry.change_type] || changeColors.changed;
  const pathParts = entry.path.split(".");

  return (
    <details open={defaultOpen}>
      <summary
        className="flex items-center gap-3 px-4 py-3 cursor-pointer select-none"
        style={{
          backgroundColor: "#111318",
          borderRadius: "8px",
          border: "1px solid #FFFFFF0A",
        }}
      >
        {/* Change type badge */}
        <span
          className="text-[10px] uppercase font-medium px-2 py-0.5 rounded-full shrink-0"
          style={{
            backgroundColor: colors.bg,
            color: colors.text,
            fontFamily: "'Inter', sans-serif",
            letterSpacing: "0.04em",
          }}
        >
          {colors.label}
        </span>

        {/* Path breadcrumb */}
        <div className="flex items-center gap-1 flex-1 min-w-0">
          {pathParts.map((part, i) => (
            <span key={i} className="flex items-center gap-1">
              {i > 0 && (
                <span className="text-[11px]" style={{ color: "#4E5060" }}>
                  ›
                </span>
              )}
              <span
                className="text-[12px]"
                style={{
                  color: i === pathParts.length - 1 ? "#ECECEE" : "#6E6E76",
                  fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                }}
              >
                {part}
              </span>
            </span>
          ))}
        </div>

        {/* Chevron */}
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="shrink-0" style={{ color: "#4E5060" }}>
          <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </summary>

      {/* Value panels */}
      <div className="flex gap-2 mt-2 px-1">
        {/* Old value */}
        {entry.change_type !== "added" && (
          <div
            className="flex-1 rounded-lg p-3 overflow-auto"
            style={{
              backgroundColor: "#E85D5D08",
              border: "1px solid #E85D5D1A",
              maxHeight: "180px",
            }}
          >
            <span
              className="text-[10px] uppercase block mb-1.5"
              style={{ color: "#E85D5D", fontFamily: "'Inter', sans-serif", letterSpacing: "0.04em" }}
            >
              old
            </span>
            <pre
              className="text-[11px] whitespace-pre-wrap break-all"
              style={{
                color: "#E85D5D99",
                fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
              }}
            >
              {formatValue(entry.old_value)}
            </pre>
          </div>
        )}

        {/* New value */}
        {entry.change_type !== "removed" && (
          <div
            className="flex-1 rounded-lg p-3 overflow-auto"
            style={{
              backgroundColor: "#4ADE8008",
              border: "1px solid #4ADE801A",
              maxHeight: "180px",
            }}
          >
            <span
              className="text-[10px] uppercase block mb-1.5"
              style={{ color: "#4ADE80", fontFamily: "'Inter', sans-serif", letterSpacing: "0.04em" }}
            >
              new
            </span>
            <pre
              className="text-[11px] whitespace-pre-wrap break-all"
              style={{
                color: "#4ADE8099",
                fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
              }}
            >
              {formatValue(entry.new_value)}
            </pre>
          </div>
        )}
      </div>
    </details>
  );
}

export function DiffPanel({ diff }: { diff: StateDiff }) {
  if (!diff.entries.length) {
    return (
      <div
        className="flex items-center justify-center py-12 rounded-lg"
        style={{ backgroundColor: "#111318", border: "1px solid #FFFFFF0A" }}
      >
        <span className="text-[13px]" style={{ color: "#4E5060", fontFamily: "'Inter', sans-serif" }}>
          No differences found
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <DiffSummaryBar entries={diff.entries} />
      <div className="flex flex-col gap-2">
        {diff.entries.map((entry, i) => (
          <DiffEntryCard key={entry.path + i} entry={entry} defaultOpen={i < 3} />
        ))}
      </div>
    </div>
  );
}
