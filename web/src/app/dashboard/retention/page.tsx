"use client";

import { useState } from "react";

const CARD_STYLE = {
  backgroundColor: "#111318",
  border: "1px solid #FFFFFF0A",
  borderRadius: "10px",
  padding: "20px",
} as const;

const LABEL_STYLE = {
  color: "#6E6E76",
  fontFamily: "'Inter', sans-serif",
  fontSize: "11px",
  fontWeight: 500,
  letterSpacing: "0.04em",
  textTransform: "uppercase" as const,
};

const INPUT_STYLE = {
  backgroundColor: "#FFFFFF08",
  border: "1px solid #FFFFFF0A",
  borderRadius: "6px",
  color: "#ECECEE",
  fontFamily: "'Inter', sans-serif",
  fontSize: "12px",
  padding: "6px 10px",
  outline: "none",
  width: "100%",
} as const;

interface PolicyForm {
  maxCommitAge: string;
  maxCommitsPerBranch: string;
  protectedBranches: string;
  maxLogAge: string;
  maxLogEntries: string;
  autoSquash: boolean;
}

interface PreviewResult {
  commitsToExpire: number;
  commitsRetained: number;
  objectsToDelete: number;
  logsToPrune: number;
  storageBefore: string;
  storageAfter: string;
  storageSavedPct: number;
}

function computePreview(form: PolicyForm): PreviewResult {
  const maxAge = parseInt(form.maxCommitAge) || 30;
  const maxPer = parseInt(form.maxCommitsPerBranch) || 100;
  const maxLogAge = parseInt(form.maxLogAge) || 7;
  const maxLogEntries = parseInt(form.maxLogEntries) || 10000;

  const baseExpire = Math.round((1247 * (30 / Math.max(maxAge, 1))) * 0.02 + (1247 / Math.max(maxPer, 1)) * 0.4);
  const commitsToExpire = Math.min(Math.max(Math.round(baseExpire), 5), 400);
  const commitsRetained = 1247 - commitsToExpire;
  const objectsToDelete = commitsToExpire * 2;
  const logsToPrune = Math.min(Math.round(4521 * (7 / Math.max(maxLogAge, 1)) * 0.42 + (4521 - Math.min(maxLogEntries, 4521)) * 0.5), 4521);
  const savedMB = (objectsToDelete * 0.09) + (logsToPrune * 0.001);
  const storageBefore = 12.4;
  const storageAfter = Math.max(storageBefore - savedMB, 1.2);
  const storageSavedPct = Math.round(((storageBefore - storageAfter) / storageBefore) * 100);

  return {
    commitsToExpire,
    commitsRetained,
    objectsToDelete,
    logsToPrune,
    storageBefore: storageBefore.toFixed(1) + " MB",
    storageAfter: storageAfter.toFixed(1) + " MB",
    storageSavedPct,
  };
}

export default function RetentionPage() {
  const [policy, setPolicy] = useState<PolicyForm>({
    maxCommitAge: "30",
    maxCommitsPerBranch: "100",
    protectedBranches: "main, production",
    maxLogAge: "7",
    maxLogEntries: "10000",
    autoSquash: false,
  });

  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [enforced, setEnforced] = useState(false);

  function handlePreview() {
    setPreviewing(true);
    setTimeout(() => {
      setPreview(computePreview(policy));
      setPreviewing(false);
    }, 600);
  }

  function handleEnforce() {
    setEnforced(true);
    setTimeout(() => setEnforced(false), 2000);
  }

  const protectedTags = policy.protectedBranches
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

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
            Retention & Maintenance
          </span>
          <span
            className="text-[12px] mt-1 block"
            style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif" }}
          >
            Manage schema versions, storage, and data lifecycle policies
          </span>
        </div>
      </div>

      {/* Top row: Schema Version + Storage Overview */}
      <div className="grid grid-cols-2 gap-4">
        {/* Schema Version Card */}
        <div style={CARD_STYLE}>
          <div className="flex items-start justify-between mb-4">
            <div>
              <span
                className="block text-[11px] uppercase font-medium mb-2"
                style={LABEL_STYLE}
              >
                Schema Version
              </span>
              <div className="flex items-end gap-2">
                <span
                  style={{
                    color: "#ECECEE",
                    fontFamily: "var(--font-display, 'Space Grotesk', sans-serif)",
                    fontSize: "48px",
                    fontWeight: 700,
                    lineHeight: 1,
                  }}
                >
                  v2
                </span>
                <span
                  className="mb-1"
                  style={{
                    color: "#4ADE80",
                    fontFamily: "'Inter', sans-serif",
                    fontSize: "11px",
                    backgroundColor: "#4ADE8012",
                    border: "1px solid #4ADE8020",
                    borderRadius: "4px",
                    padding: "2px 6px",
                  }}
                >
                  current
                </span>
              </div>
              <span
                className="block mt-1"
                style={{
                  color: "#6E6E76",
                  fontFamily: "'Inter', sans-serif",
                  fontSize: "12px",
                }}
              >
                Last migrated: 2h ago
              </span>
            </div>
            <button
              className="flex items-center gap-1.5 py-1.5 px-3 rounded-[6px] text-[12px] font-medium"
              style={{
                backgroundColor: "#5B8DEF18",
                color: "#5B8DEF",
                border: "1px solid #5B8DEF30",
                fontFamily: "'Inter', sans-serif",
                cursor: "pointer",
              }}
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path
                  d="M2 6C2 3.79 3.79 2 6 2C7.5 2 8.8 2.8 9.5 4"
                  stroke="currentColor"
                  strokeWidth="1.3"
                  strokeLinecap="round"
                />
                <path
                  d="M10 6C10 8.21 8.21 10 6 10C4.5 10 3.2 9.2 2.5 8"
                  stroke="currentColor"
                  strokeWidth="1.3"
                  strokeLinecap="round"
                />
                <path
                  d="M9.5 2.5L9.5 4.5L7.5 4.5"
                  stroke="currentColor"
                  strokeWidth="1.3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M2.5 9.5L2.5 7.5L4.5 7.5"
                  stroke="currentColor"
                  strokeWidth="1.3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              Run Migrations
            </button>
          </div>

          {/* Migration history */}
          <div
            style={{
              borderTop: "1px solid #FFFFFF0A",
              paddingTop: "14px",
            }}
          >
            <span
              className="block mb-2 uppercase"
              style={LABEL_STYLE}
            >
              Migration History
            </span>
            {[
              {
                from: "v1",
                to: "v2",
                desc: "Add schema_version table",
                ts: "2h ago",
                ok: true,
              },
              {
                from: "v0",
                to: "v1",
                desc: "Initialize object store",
                ts: "14d ago",
                ok: true,
              },
            ].map((m, i) => (
              <div
                key={i}
                className="flex items-center justify-between py-2"
                style={{
                  borderBottom: i === 0 ? "1px solid #FFFFFF08" : "none",
                }}
              >
                <div className="flex items-center gap-2">
                  <span
                    style={{
                      color: "#A0A0AA",
                      fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                      fontSize: "11px",
                    }}
                  >
                    {m.from}
                  </span>
                  <svg width="12" height="8" viewBox="0 0 12 8" fill="none">
                    <path
                      d="M1 4h9M7.5 1.5L10 4L7.5 6.5"
                      stroke="#4E5060"
                      strokeWidth="1.2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  <span
                    style={{
                      color: "#5B8DEF",
                      fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                      fontSize: "11px",
                    }}
                  >
                    {m.to}
                  </span>
                  <span
                    style={{
                      color: "#A0A0AA",
                      fontFamily: "'Inter', sans-serif",
                      fontSize: "12px",
                    }}
                  >
                    {m.desc}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    style={{
                      color: "#6E6E76",
                      fontFamily: "'Inter', sans-serif",
                      fontSize: "11px",
                    }}
                  >
                    {m.ts}
                  </span>
                  <span
                    style={{
                      color: "#4ADE80",
                      fontSize: "10px",
                      backgroundColor: "#4ADE8012",
                      border: "1px solid #4ADE8020",
                      borderRadius: "4px",
                      padding: "1px 5px",
                      fontFamily: "'Inter', sans-serif",
                    }}
                  >
                    ok
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Storage Overview Card */}
        <div style={CARD_STYLE}>
          <span
            className="block text-[11px] uppercase font-medium mb-4"
            style={LABEL_STYLE}
          >
            Storage Overview
          </span>

          <div className="grid grid-cols-2 gap-3 mb-4">
            {[
              { label: "Total Objects", value: "1,247", color: "#5B8DEF" },
              { label: "Total Refs", value: "8", color: "#A0A0AA" },
              { label: "Log Entries", value: "4,521", color: "#E8A44A" },
              { label: "Database Size", value: "12.4 MB", color: "#ECECEE" },
            ].map((stat) => (
              <div
                key={stat.label}
                className="flex flex-col gap-1 p-3 rounded-[7px]"
                style={{ backgroundColor: "#FFFFFF05", border: "1px solid #FFFFFF08" }}
              >
                <span
                  style={{
                    color: "#6E6E76",
                    fontFamily: "'Inter', sans-serif",
                    fontSize: "10px",
                    letterSpacing: "0.04em",
                    textTransform: "uppercase",
                  }}
                >
                  {stat.label}
                </span>
                <span
                  style={{
                    color: stat.color,
                    fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                    fontSize: "18px",
                    fontWeight: 600,
                  }}
                >
                  {stat.value}
                </span>
              </div>
            ))}
          </div>

          {/* Object type bars */}
          <div
            style={{
              borderTop: "1px solid #FFFFFF0A",
              paddingTop: "14px",
            }}
          >
            <span
              className="block mb-3 uppercase"
              style={LABEL_STYLE}
            >
              Object Breakdown
            </span>
            {[
              { label: "Commits", count: 312, total: 1247, color: "#5B8DEF" },
              { label: "Blobs", count: 891, total: 1247, color: "#E8A44A" },
              { label: "Trees", count: 44, total: 1247, color: "#A0A0AA" },
            ].map((obj) => {
              const pct = Math.round((obj.count / obj.total) * 100);
              return (
                <div key={obj.label} className="mb-2">
                  <div className="flex items-center justify-between mb-1">
                    <span
                      style={{
                        color: "#A0A0AA",
                        fontFamily: "'Inter', sans-serif",
                        fontSize: "11px",
                      }}
                    >
                      {obj.label}
                    </span>
                    <span
                      style={{
                        color: "#6E6E76",
                        fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                        fontSize: "11px",
                      }}
                    >
                      {obj.count.toLocaleString()} ({pct}%)
                    </span>
                  </div>
                  <div
                    className="rounded-full overflow-hidden"
                    style={{ height: "4px", backgroundColor: "#FFFFFF0A" }}
                  >
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${pct}%`,
                        backgroundColor: obj.color,
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Retention Policy Card */}
      <div style={CARD_STYLE}>
        <div className="flex items-center justify-between mb-4">
          <span
            className="text-[13px] font-semibold"
            style={{
              color: "#ECECEE",
              fontFamily: "var(--font-display, 'Space Grotesk', sans-serif)",
            }}
          >
            Retention Policy
          </span>
          <div className="flex items-center gap-1.5">
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: "#E8A44A" }}
            />
            <span
              style={{
                color: "#E8A44A",
                fontFamily: "'Inter', sans-serif",
                fontSize: "11px",
              }}
            >
              Not enforced — preview before applying
            </span>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4">
          {/* Max Commit Age */}
          <div className="flex flex-col gap-1.5">
            <label style={LABEL_STYLE}>Max Commit Age</label>
            <div className="relative">
              <input
                type="text"
                value={policy.maxCommitAge}
                onChange={(e) =>
                  setPolicy((p) => ({ ...p, maxCommitAge: e.target.value }))
                }
                style={INPUT_STYLE}
              />
              <span
                className="absolute right-2.5 top-1/2 -translate-y-1/2"
                style={{
                  color: "#4E5060",
                  fontFamily: "'Inter', sans-serif",
                  fontSize: "11px",
                }}
              >
                days
              </span>
            </div>
          </div>

          {/* Max Commits Per Branch */}
          <div className="flex flex-col gap-1.5">
            <label style={LABEL_STYLE}>Max Commits / Branch</label>
            <input
              type="text"
              value={policy.maxCommitsPerBranch}
              onChange={(e) =>
                setPolicy((p) => ({ ...p, maxCommitsPerBranch: e.target.value }))
              }
              style={INPUT_STYLE}
            />
          </div>

          {/* Max Log Age */}
          <div className="flex flex-col gap-1.5">
            <label style={LABEL_STYLE}>Max Log Age</label>
            <div className="relative">
              <input
                type="text"
                value={policy.maxLogAge}
                onChange={(e) =>
                  setPolicy((p) => ({ ...p, maxLogAge: e.target.value }))
                }
                style={INPUT_STYLE}
              />
              <span
                className="absolute right-2.5 top-1/2 -translate-y-1/2"
                style={{
                  color: "#4E5060",
                  fontFamily: "'Inter', sans-serif",
                  fontSize: "11px",
                }}
              >
                days
              </span>
            </div>
          </div>

          {/* Max Log Entries */}
          <div className="flex flex-col gap-1.5">
            <label style={LABEL_STYLE}>Max Log Entries</label>
            <input
              type="text"
              value={policy.maxLogEntries}
              onChange={(e) =>
                setPolicy((p) => ({ ...p, maxLogEntries: e.target.value }))
              }
              style={INPUT_STYLE}
            />
          </div>

          {/* Protected Branches */}
          <div className="flex flex-col gap-1.5">
            <label style={LABEL_STYLE}>Protected Branches</label>
            <input
              type="text"
              value={policy.protectedBranches}
              onChange={(e) =>
                setPolicy((p) => ({ ...p, protectedBranches: e.target.value }))
              }
              placeholder="e.g. main, production"
              style={INPUT_STYLE}
            />
            <div className="flex flex-wrap gap-1 mt-0.5">
              {protectedTags.map((tag) => (
                <span
                  key={tag}
                  style={{
                    backgroundColor: "#5B8DEF14",
                    border: "1px solid #5B8DEF28",
                    borderRadius: "4px",
                    color: "#5B8DEF",
                    fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                    fontSize: "10px",
                    padding: "1px 6px",
                  }}
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>

          {/* Auto-squash toggle */}
          <div className="flex flex-col gap-1.5">
            <label style={LABEL_STYLE}>Auto-squash</label>
            <div className="flex items-center gap-3 mt-1">
              <button
                onClick={() =>
                  setPolicy((p) => ({ ...p, autoSquash: !p.autoSquash }))
                }
                className="relative shrink-0"
                style={{
                  width: "36px",
                  height: "20px",
                  borderRadius: "10px",
                  backgroundColor: policy.autoSquash ? "#5B8DEF" : "#FFFFFF14",
                  border: "none",
                  cursor: "pointer",
                  transition: "background-color 0.2s",
                }}
              >
                <span
                  style={{
                    position: "absolute",
                    top: "3px",
                    left: policy.autoSquash ? "19px" : "3px",
                    width: "14px",
                    height: "14px",
                    borderRadius: "50%",
                    backgroundColor: "#ECECEE",
                    transition: "left 0.2s",
                  }}
                />
              </button>
              <span
                style={{
                  color: policy.autoSquash ? "#ECECEE" : "#6E6E76",
                  fontFamily: "'Inter', sans-serif",
                  fontSize: "12px",
                }}
              >
                {policy.autoSquash ? "Enabled" : "Disabled"}
              </span>
            </div>
            <span
              style={{
                color: "#4E5060",
                fontFamily: "'Inter', sans-serif",
                fontSize: "11px",
              }}
            >
              Merge sequential commits before pruning
            </span>
          </div>
        </div>

        {/* Action Buttons */}
        <div
          className="flex items-center gap-2.5 mt-5 pt-4"
          style={{ borderTop: "1px solid #FFFFFF0A" }}
        >
          <button
            onClick={handlePreview}
            disabled={previewing}
            className="flex items-center gap-1.5 py-1.5 px-4 rounded-[6px] text-[12px] font-medium"
            style={{
              backgroundColor: "#FFFFFF0A",
              color: "#A0A0AA",
              border: "1px solid #FFFFFF14",
              fontFamily: "'Inter', sans-serif",
              cursor: previewing ? "wait" : "pointer",
              opacity: previewing ? 0.7 : 1,
            }}
          >
            {previewing ? (
              <>
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 12 12"
                  fill="none"
                  className="animate-spin"
                >
                  <circle
                    cx="6"
                    cy="6"
                    r="4.5"
                    stroke="currentColor"
                    strokeWidth="1.3"
                    strokeOpacity="0.3"
                  />
                  <path
                    d="M10.5 6A4.5 4.5 0 016 1.5"
                    stroke="currentColor"
                    strokeWidth="1.3"
                    strokeLinecap="round"
                  />
                </svg>
                Computing...
              </>
            ) : (
              <>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                  <circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1.3" />
                  <path
                    d="M4.5 6L5.5 7L7.5 5"
                    stroke="currentColor"
                    strokeWidth="1.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                Preview
              </>
            )}
          </button>
          <button
            className="flex items-center gap-1.5 py-1.5 px-4 rounded-[6px] text-[12px] font-medium"
            style={{
              backgroundColor: "#FFFFFF05",
              color: "#6E6E76",
              border: "1px solid #FFFFFF0A",
              fontFamily: "'Inter', sans-serif",
              cursor: "pointer",
            }}
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <path
                d="M2 6h8M6 2v8"
                stroke="currentColor"
                strokeWidth="1.3"
                strokeLinecap="round"
              />
            </svg>
            Enforce
          </button>
        </div>
      </div>

      {/* Preview Results Card */}
      {preview && (
        <div
          style={{
            ...CARD_STYLE,
            border: "1px solid #E85D5D20",
          }}
        >
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <span
                className="text-[13px] font-semibold"
                style={{
                  color: "#ECECEE",
                  fontFamily: "var(--font-display, 'Space Grotesk', sans-serif)",
                }}
              >
                Preview Results
              </span>
              <span
                style={{
                  backgroundColor: "#E8A44A12",
                  border: "1px solid #E8A44A24",
                  borderRadius: "4px",
                  color: "#E8A44A",
                  fontFamily: "'Inter', sans-serif",
                  fontSize: "10px",
                  fontWeight: 500,
                  padding: "1px 6px",
                  letterSpacing: "0.04em",
                  textTransform: "uppercase",
                }}
              >
                Dry Run
              </span>
            </div>
            <span
              style={{
                color: "#6E6E76",
                fontFamily: "'Inter', sans-serif",
                fontSize: "11px",
              }}
            >
              Simulated — no changes applied
            </span>
          </div>

          <div className="grid grid-cols-5 gap-3 mb-5">
            {[
              {
                label: "Commits to Expire",
                value: preview.commitsToExpire,
                color: "#E85D5D",
              },
              {
                label: "Commits Retained",
                value: preview.commitsRetained.toLocaleString(),
                color: "#4ADE80",
              },
              {
                label: "Objects to Delete",
                value: preview.objectsToDelete,
                color: "#E8A44A",
              },
              {
                label: "Logs to Prune",
                value: preview.logsToPrune.toLocaleString(),
                color: "#E8A44A",
              },
              {
                label: "Storage Saved",
                value: `${preview.storageSavedPct}%`,
                color: "#4ADE80",
              },
            ].map((stat) => (
              <div
                key={stat.label}
                className="flex flex-col gap-1 p-3 rounded-[7px]"
                style={{ backgroundColor: "#FFFFFF04", border: "1px solid #FFFFFF08" }}
              >
                <span
                  style={{
                    color: "#6E6E76",
                    fontFamily: "'Inter', sans-serif",
                    fontSize: "10px",
                    letterSpacing: "0.04em",
                    textTransform: "uppercase",
                  }}
                >
                  {stat.label}
                </span>
                <span
                  style={{
                    color: stat.color,
                    fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                    fontSize: "20px",
                    fontWeight: 600,
                  }}
                >
                  {stat.value}
                </span>
              </div>
            ))}
          </div>

          {/* Storage bar */}
          <div className="mb-5">
            <div className="flex items-center justify-between mb-2">
              <span
                style={{
                  color: "#A0A0AA",
                  fontFamily: "'Inter', sans-serif",
                  fontSize: "12px",
                }}
              >
                Storage: {preview.storageBefore}
                <span style={{ color: "#4E5060", margin: "0 6px" }}>→</span>
                <span style={{ color: "#4ADE80" }}>{preview.storageAfter}</span>
              </span>
              <span
                style={{
                  color: "#4ADE80",
                  fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                  fontSize: "11px",
                }}
              >
                -{preview.storageSavedPct}%
              </span>
            </div>
            <div
              className="rounded-full overflow-hidden relative"
              style={{ height: "8px", backgroundColor: "#FFFFFF0A" }}
            >
              {/* Before bar (full width faint) */}
              <div
                className="absolute inset-0 rounded-full"
                style={{ backgroundColor: "#E85D5D18", width: "100%" }}
              />
              {/* After bar */}
              <div
                className="h-full rounded-full"
                style={{
                  width: `${100 - preview.storageSavedPct}%`,
                  backgroundColor: "#4ADE80",
                  transition: "width 0.4s ease",
                }}
              />
            </div>
            <div className="flex items-center gap-4 mt-1.5">
              <div className="flex items-center gap-1.5">
                <span
                  className="w-2 h-2 rounded-sm"
                  style={{ backgroundColor: "#E85D5D18", border: "1px solid #E85D5D40" }}
                />
                <span style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif", fontSize: "10px" }}>
                  Before ({preview.storageBefore})
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <span
                  className="w-2 h-2 rounded-sm"
                  style={{ backgroundColor: "#4ADE8030" }}
                />
                <span style={{ color: "#6E6E76", fontFamily: "'Inter', sans-serif", fontSize: "10px" }}>
                  After ({preview.storageAfter})
                </span>
              </div>
            </div>
          </div>

          {/* Enforce Now danger button */}
          <div
            className="flex items-center justify-between pt-4"
            style={{ borderTop: "1px solid #FFFFFF0A" }}
          >
            <div className="flex items-center gap-2">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path
                  d="M7 2L12.5 11.5H1.5L7 2Z"
                  stroke="#E85D5D"
                  strokeWidth="1.3"
                  strokeLinejoin="round"
                />
                <line
                  x1="7"
                  y1="6"
                  x2="7"
                  y2="9"
                  stroke="#E85D5D"
                  strokeWidth="1.3"
                  strokeLinecap="round"
                />
                <circle cx="7" cy="10.5" r="0.6" fill="#E85D5D" />
              </svg>
              <span
                style={{
                  color: "#6E6E76",
                  fontFamily: "'Inter', sans-serif",
                  fontSize: "11px",
                }}
              >
                This will permanently delete {preview.commitsToExpire} commits and {preview.objectsToDelete} objects.
              </span>
            </div>
            <button
              onClick={handleEnforce}
              className="flex items-center gap-1.5 py-1.5 px-4 rounded-[6px] text-[12px] font-medium"
              style={{
                backgroundColor: enforced ? "#4ADE8018" : "#E85D5D18",
                color: enforced ? "#4ADE80" : "#E85D5D",
                border: `1px solid ${enforced ? "#4ADE8030" : "#E85D5D30"}`,
                fontFamily: "'Inter', sans-serif",
                cursor: "pointer",
                transition: "all 0.2s",
              }}
            >
              {enforced ? (
                <>
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                    <path
                      d="M2 6L5 9L10 3"
                      stroke="currentColor"
                      strokeWidth="1.4"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  Enforced
                </>
              ) : (
                <>
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                    <path
                      d="M2 3h8M4.5 3V2h3v1M5 5v4M7 5v4"
                      stroke="currentColor"
                      strokeWidth="1.2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                    <path
                      d="M3 3l.5 7h5l.5-7"
                      stroke="currentColor"
                      strokeWidth="1.2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  Enforce Now
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Empty preview state */}
      {!preview && (
        <div
          className="flex flex-col items-center justify-center py-10 rounded-[10px]"
          style={{ border: "1px dashed #FFFFFF0A" }}
        >
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none" className="mb-3">
            <circle cx="16" cy="16" r="13" stroke="#FFFFFF14" strokeWidth="1.5" />
            <path
              d="M10 16h12M16 10v12"
              stroke="#4E5060"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
          <span
            style={{
              color: "#4E5060",
              fontFamily: "'Inter', sans-serif",
              fontSize: "12px",
            }}
          >
            Adjust the policy above and click <strong style={{ color: "#6E6E76" }}>Preview</strong> to simulate results
          </span>
        </div>
      )}
    </div>
  );
}
