export interface Commit {
  hash: string;
  message: string;
  author: string;
  timestamp: string;
  action_type: string;
  parent_hashes: string[];
}

export interface DiffEntry {
  path: string;
  change_type: "added" | "removed" | "changed";
  old_value: unknown;
  new_value: unknown;
}

export interface StateDiff {
  base_hash: string;
  target_hash: string;
  entries: DiffEntry[];
}

export interface AuditEntry {
  id: string;
  timestamp: string;
  agent_id: string;
  action: string;
  message: string;
  commit_hash: string | null;
  level: string;
}

export interface Branch {
  name: string;
  hash: string;
  is_current: boolean;
}

export interface HealthStatus {
  status: string;
  version: string;
  uptime?: number;
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const API_KEY = process.env.NEXT_PUBLIC_AGIT_API_KEY;
export const USE_DEMO_DATA =
  process.env.NEXT_PUBLIC_AGIT_USE_DEMO_DATA === "1";

interface BranchListResponse {
  branches: Record<string, string>;
  current?: string | null;
}

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    ...(options?.headers as Record<string, string> | undefined),
  };
  if (API_KEY) {
    headers["X-API-Key"] = API_KEY;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    headers,
    ...options,
  });
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  getCommits: (limit = 50) =>
    fetchApi<{ commits: Commit[] }>(`/commits?limit=${limit}`),
  getCommit: (hash: string) =>
    fetchApi<{ commit: Commit; state: Record<string, unknown> }>(
      `/commits/${hash}`
    ),
  getDiff: (h1: string, h2: string) =>
    fetchApi<StateDiff>(`/diff?hash1=${h1}&hash2=${h2}`),
  getBranches: async () => {
    const data = await fetchApi<BranchListResponse>("/branches");
    const branches: Branch[] = Object.entries(data.branches || {}).map(
      ([name, hash]) => ({
        name,
        hash,
        is_current: data.current === name,
      })
    );
    return { branches };
  },
  getAudit: (limit = 100) =>
    fetchApi<{ entries: AuditEntry[] }>(`/audit?limit=${limit}`),
  getHealth: () => fetchApi<HealthStatus>("/health"),
};

// Demo data for when API is not connected
function makeDemoData() {
  const now = Date.now();
  return {
    commits: [
      { hash: "f5ad9261ee742575", message: "weather API response", author: "demo-agent", timestamp: new Date(now - 120000).toISOString(), action_type: "llm_response", parent_hashes: ["3b82f6a0"] },
      { hash: "3b82f6a0ee8d1234", message: "calling weather API", author: "demo-agent", timestamp: new Date(now - 240000).toISOString(), action_type: "tool_call", parent_hashes: ["a1c2d3e4"] },
      { hash: "a1c2d3e4ff556677", message: "user input received", author: "demo-agent", timestamp: new Date(now - 360000).toISOString(), action_type: "user_input", parent_hashes: [] },
      { hash: "9e8d7c6b5a4f3e2d", message: "summary generated", author: "research-agent", timestamp: new Date(now - 480000).toISOString(), action_type: "llm_response", parent_hashes: ["1f2e3d4c"] },
      { hash: "1f2e3d4c5b6a7890", message: "document summary request", author: "research-agent", timestamp: new Date(now - 600000).toISOString(), action_type: "user_input", parent_hashes: [] },
      { hash: "ab12cd34ef567890", message: "retry attempt 1 succeeded", author: "demo-agent", timestamp: new Date(now - 720000).toISOString(), action_type: "tool_call", parent_hashes: ["f5ad9261"] },
      { hash: "dead0000beef1111", message: "pre-retry-base: process data", author: "demo-agent", timestamp: new Date(now - 840000).toISOString(), action_type: "checkpoint", parent_hashes: [] },
      { hash: "cafe0000babe2222", message: "agent state checkpoint", author: "monitor-agent", timestamp: new Date(now - 960000).toISOString(), action_type: "checkpoint", parent_hashes: [] },
    ] as Commit[],
    branches: [
      { name: "main", hash: "f5ad9261ee742575", is_current: true },
      { name: "retry/a1b2c3/attempt-1", hash: "ab12cd34ef567890", is_current: false },
      { name: "feature/summarize", hash: "9e8d7c6b5a4f3e2d", is_current: false },
    ] as Branch[],
    audit: [
      { id: "log-001", timestamp: new Date(now - 120000).toISOString(), agent_id: "demo-agent", action: "llm_response", message: "weather API response", commit_hash: "f5ad9261", level: "info" },
      { id: "log-002", timestamp: new Date(now - 240000).toISOString(), agent_id: "demo-agent", action: "tool_call", message: "calling weather API", commit_hash: "3b82f6a0", level: "info" },
      { id: "log-003", timestamp: new Date(now - 360000).toISOString(), agent_id: "demo-agent", action: "user_input", message: "user input received", commit_hash: "a1c2d3e4", level: "info" },
      { id: "log-004", timestamp: new Date(now - 480000).toISOString(), agent_id: "research-agent", action: "llm_response", message: "summary generated", commit_hash: "9e8d7c6b", level: "info" },
      { id: "log-005", timestamp: new Date(now - 600000).toISOString(), agent_id: "research-agent", action: "user_input", message: "document summary request", commit_hash: "1f2e3d4c", level: "info" },
      { id: "log-006", timestamp: new Date(now - 720000).toISOString(), agent_id: "demo-agent", action: "tool_call", message: "retry attempt 1 succeeded", commit_hash: "ab12cd34", level: "warning" },
      { id: "log-007", timestamp: new Date(now - 840000).toISOString(), agent_id: "demo-agent", action: "checkpoint", message: "pre-retry-base: process data", commit_hash: "dead0000", level: "info" },
      { id: "log-008", timestamp: new Date(now - 960000).toISOString(), agent_id: "monitor-agent", action: "checkpoint", message: "agent state checkpoint", commit_hash: "cafe0000", level: "info" },
    ] as AuditEntry[],
  };
}

export function getDemoData() {
  return makeDemoData();
}
