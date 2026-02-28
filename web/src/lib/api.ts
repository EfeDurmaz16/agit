export interface Commit {
  hash: string;
  message: string;
  author: string;
  timestamp: string;
  action_type: string;
  parent_hashes: string[];
  branch?: string;
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
  type?: string;
}

export interface HealthStatus {
  status: string;
  version: string;
  uptime?: number;
}

export interface ReplayStep {
  commit: Commit;
  state: Record<string, unknown>;
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
  search: (query: string) =>
    fetchApi<{ commits: Commit[]; audit: AuditEntry[] }>(
      `/search?q=${encodeURIComponent(query)}`
    ),
};

// ---------------------------------------------------------------------------
// Demo data
// ---------------------------------------------------------------------------
function makeDemoData() {
  const now = Date.now();
  const m = (offset: number) => new Date(now - offset * 60000).toISOString();

  const commits: Commit[] = [
    // main branch — linear chain
    { hash: "f5ad9261ee742575", message: "weather API response parsed", author: "demo-agent", timestamp: m(2), action_type: "llm_response", parent_hashes: ["3b82f6a0ee8d1234"], branch: "main" },
    { hash: "3b82f6a0ee8d1234", message: "calling weather API", author: "demo-agent", timestamp: m(4), action_type: "tool_call", parent_hashes: ["a1c2d3e4ff556677"], branch: "main" },
    { hash: "a1c2d3e4ff556677", message: "user asks for weather forecast", author: "demo-agent", timestamp: m(6), action_type: "user_input", parent_hashes: ["7788aabb11223344"], branch: "main" },
    { hash: "7788aabb11223344", message: "session initialized", author: "demo-agent", timestamp: m(8), action_type: "checkpoint", parent_hashes: ["cc11dd22ee33ff44"], branch: "main" },
    { hash: "cc11dd22ee33ff44", message: "config loaded from env", author: "demo-agent", timestamp: m(10), action_type: "tool_call", parent_hashes: ["dd22ee33ff445566"], branch: "main" },
    { hash: "dd22ee33ff445566", message: "agent bootstrap complete", author: "demo-agent", timestamp: m(12), action_type: "checkpoint", parent_hashes: [], branch: "main" },

    // retry branch — forks from 3b82f6a0
    { hash: "ab12cd34ef567890", message: "retry: re-calling weather API", author: "demo-agent", timestamp: m(3), action_type: "tool_call", parent_hashes: ["3b82f6a0ee8d1234"], branch: "retry/weather/attempt-1" },
    { hash: "ef56789012345678", message: "retry: got cached response", author: "demo-agent", timestamp: m(2.5), action_type: "llm_response", parent_hashes: ["ab12cd34ef567890"], branch: "retry/weather/attempt-1" },

    // feature/summarize branch — forks from 7788aabb
    { hash: "9e8d7c6b5a4f3e2d", message: "summary generated", author: "research-agent", timestamp: m(7), action_type: "llm_response", parent_hashes: ["1f2e3d4c5b6a7890"], branch: "feature/summarize" },
    { hash: "1f2e3d4c5b6a7890", message: "document summary request", author: "research-agent", timestamp: m(9), action_type: "user_input", parent_hashes: ["7788aabb11223344"], branch: "feature/summarize" },
    { hash: "aabb112233445566", message: "extracting key sections", author: "research-agent", timestamp: m(8), action_type: "tool_call", parent_hashes: ["1f2e3d4c5b6a7890"], branch: "feature/summarize" },
    { hash: "bbcc223344556677", message: "NLP model loaded", author: "research-agent", timestamp: m(7.5), action_type: "tool_call", parent_hashes: ["aabb112233445566"], branch: "feature/summarize" },

    // rollback branch — forks from cc11dd22
    { hash: "dead0000beef1111", message: "rollback: reverting trade #2841", author: "compliance-agent", timestamp: m(11), action_type: "rollback", parent_hashes: ["cc11dd22ee33ff44"], branch: "rollback/trade-2841" },
    { hash: "cafe0000babe2222", message: "rollback: state restored", author: "compliance-agent", timestamp: m(10.5), action_type: "checkpoint", parent_hashes: ["dead0000beef1111"], branch: "rollback/trade-2841" },

    // experiment branch — forks from a1c2d3e4, merges back
    { hash: "1122334455667788", message: "experiment: trying new parser", author: "demo-agent", timestamp: m(5.5), action_type: "tool_call", parent_hashes: ["a1c2d3e4ff556677"], branch: "experiment/parser" },
    { hash: "2233445566778899", message: "experiment: parser validated", author: "demo-agent", timestamp: m(5), action_type: "llm_response", parent_hashes: ["1122334455667788"], branch: "experiment/parser" },
    { hash: "33445566778899aa", message: "merge: experiment/parser into main", author: "demo-agent", timestamp: m(4.5), action_type: "checkpoint", parent_hashes: ["2233445566778899", "3b82f6a0ee8d1234"], branch: "main" },

    // more main commits after merge
    { hash: "4455667788990011", message: "formatting output for user", author: "demo-agent", timestamp: m(1.5), action_type: "llm_response", parent_hashes: ["f5ad9261ee742575"], branch: "main" },
    { hash: "5566778899001122", message: "final response delivered", author: "demo-agent", timestamp: m(1), action_type: "llm_response", parent_hashes: ["4455667788990011"], branch: "main" },
    { hash: "6677889900112233", message: "session checkpoint saved", author: "monitor-agent", timestamp: m(0.5), action_type: "checkpoint", parent_hashes: ["5566778899001122"], branch: "main" },
  ];

  const branches: Branch[] = [
    { name: "main", hash: "6677889900112233", is_current: true, type: "default" },
    { name: "retry/weather/attempt-1", hash: "ef56789012345678", is_current: false, type: "retry" },
    { name: "feature/summarize", hash: "9e8d7c6b5a4f3e2d", is_current: false, type: "feature" },
    { name: "rollback/trade-2841", hash: "cafe0000babe2222", is_current: false, type: "rollback" },
    { name: "experiment/parser", hash: "2233445566778899", is_current: false, type: "feature" },
  ];

  const audit: AuditEntry[] = [
    { id: "log-001", timestamp: m(0.5), agent_id: "monitor-agent", action: "checkpoint", message: "Session checkpoint saved", commit_hash: "66778899", level: "info" },
    { id: "log-002", timestamp: m(1), agent_id: "demo-agent", action: "llm_response", message: "Final response delivered to user", commit_hash: "55667788", level: "info" },
    { id: "log-003", timestamp: m(1.5), agent_id: "demo-agent", action: "llm_response", message: "Formatting weather output", commit_hash: "44556677", level: "info" },
    { id: "log-004", timestamp: m(2), agent_id: "demo-agent", action: "llm_response", message: "Weather API response parsed successfully", commit_hash: "f5ad9261", level: "info" },
    { id: "log-005", timestamp: m(2.5), agent_id: "demo-agent", action: "llm_response", message: "Retry: got cached response", commit_hash: "ef567890", level: "warning" },
    { id: "log-006", timestamp: m(3), agent_id: "demo-agent", action: "tool_call", message: "Retry: re-calling weather API with backoff", commit_hash: "ab12cd34", level: "warning" },
    { id: "log-007", timestamp: m(4), agent_id: "demo-agent", action: "tool_call", message: "Calling weather API — endpoint: /v2/forecast", commit_hash: "3b82f6a0", level: "info" },
    { id: "log-008", timestamp: m(4.5), agent_id: "demo-agent", action: "checkpoint", message: "Merge: experiment/parser into main", commit_hash: "33445566", level: "info" },
    { id: "log-009", timestamp: m(5), agent_id: "demo-agent", action: "llm_response", message: "Experiment: parser validated OK", commit_hash: "22334455", level: "info" },
    { id: "log-010", timestamp: m(5.5), agent_id: "demo-agent", action: "tool_call", message: "Experiment: loading new JSON parser", commit_hash: "11223344", level: "info" },
    { id: "log-011", timestamp: m(6), agent_id: "demo-agent", action: "user_input", message: "User asks for weather forecast in NYC", commit_hash: "a1c2d3e4", level: "info" },
    { id: "log-012", timestamp: m(7), agent_id: "research-agent", action: "llm_response", message: "Summary generated — 3 key findings", commit_hash: "9e8d7c6b", level: "info" },
    { id: "log-013", timestamp: m(7.5), agent_id: "research-agent", action: "tool_call", message: "NLP model loaded — sentiment pipeline", commit_hash: "bbcc2233", level: "info" },
    { id: "log-014", timestamp: m(8), agent_id: "research-agent", action: "tool_call", message: "Extracting key sections from document", commit_hash: "aabb1122", level: "info" },
    { id: "log-015", timestamp: m(8), agent_id: "demo-agent", action: "checkpoint", message: "Session initialized — agent ID assigned", commit_hash: "7788aabb", level: "info" },
    { id: "log-016", timestamp: m(9), agent_id: "research-agent", action: "user_input", message: "Document summary request received", commit_hash: "1f2e3d4c", level: "info" },
    { id: "log-017", timestamp: m(10), agent_id: "demo-agent", action: "tool_call", message: "Config loaded from environment", commit_hash: "cc11dd22", level: "info" },
    { id: "log-018", timestamp: m(10.5), agent_id: "compliance-agent", action: "checkpoint", message: "Rollback: state restored to pre-trade", commit_hash: "cafe0000", level: "warning" },
    { id: "log-019", timestamp: m(11), agent_id: "compliance-agent", action: "rollback", message: "Rollback: reverting trade #2841 — regulatory hold", commit_hash: "dead0000", level: "error" },
    { id: "log-020", timestamp: m(12), agent_id: "demo-agent", action: "checkpoint", message: "Agent bootstrap complete", commit_hash: "dd22ee33", level: "info" },
    { id: "log-021", timestamp: m(13), agent_id: "monitor-agent", action: "tool_call", message: "Health check — all systems nominal", commit_hash: null, level: "info" },
    { id: "log-022", timestamp: m(15), agent_id: "compliance-agent", action: "tool_call", message: "Scanning trade log for anomalies", commit_hash: null, level: "info" },
    { id: "log-023", timestamp: m(18), agent_id: "monitor-agent", action: "checkpoint", message: "Integrity hash chain verified — 20 commits", commit_hash: null, level: "info" },
  ];

  return { commits, branches, audit };
}

export function getDemoData() {
  return makeDemoData();
}

// ---------------------------------------------------------------------------
// Demo diff data
// ---------------------------------------------------------------------------
export function getDemoDiff(hash1: string, hash2: string): StateDiff {
  return {
    base_hash: hash1,
    target_hash: hash2,
    entries: [
      { path: "memory.last_tool_call", change_type: "changed", old_value: "weather_api_v1", new_value: "weather_api_v2" },
      { path: "memory.response_text", change_type: "changed", old_value: "Fetching forecast data...", new_value: "Today in NYC: 72°F, partly cloudy with a chance of rain in the evening." },
      { path: "world_state.api_calls_count", change_type: "changed", old_value: 3, new_value: 4 },
      { path: "world_state.cache_hit", change_type: "added", old_value: null, new_value: true },
      { path: "memory.pending_actions", change_type: "removed", old_value: ["fetch_forecast", "parse_response"], new_value: null },
      { path: "world_state.branch", change_type: "changed", old_value: "main", new_value: "main" },
      { path: "memory.tokens_used", change_type: "changed", old_value: 1247, new_value: 1891 },
      { path: "world_state.active_tools", change_type: "changed", old_value: ["weather_api"], new_value: [] },
      { path: "memory.confidence_score", change_type: "added", old_value: null, new_value: 0.94 },
      { path: "world_state.error_count", change_type: "changed", old_value: 1, new_value: 0 },
    ],
  };
}

// ---------------------------------------------------------------------------
// Demo commit state
// ---------------------------------------------------------------------------
export function getDemoCommitState(hash: string): Record<string, unknown> {
  const states: Record<string, Record<string, unknown>> = {
    "6677889900112233": {
      memory: { last_action: "checkpoint", response_text: "Session saved.", tokens_used: 2104, confidence_score: 0.97 },
      world_state: { branch: "main", api_calls_count: 5, active_tools: [], error_count: 0, cache_hit: true },
      agent: { id: "demo-agent", session_id: "sess-a8f3", uptime_ms: 720000 },
    },
    "5566778899001122": {
      memory: { last_action: "llm_response", response_text: "Today in NYC: 72°F, partly cloudy.", tokens_used: 2050, confidence_score: 0.96 },
      world_state: { branch: "main", api_calls_count: 5, active_tools: [], error_count: 0 },
      agent: { id: "demo-agent", session_id: "sess-a8f3", uptime_ms: 660000 },
    },
    "f5ad9261ee742575": {
      memory: { last_action: "llm_response", response_text: "Parsing weather data...", tokens_used: 1891, confidence_score: 0.94 },
      world_state: { branch: "main", api_calls_count: 4, active_tools: [], error_count: 0, cache_hit: true },
      agent: { id: "demo-agent", session_id: "sess-a8f3", uptime_ms: 600000 },
    },
    "3b82f6a0ee8d1234": {
      memory: { last_action: "tool_call", response_text: "Fetching forecast data...", tokens_used: 1247, pending_actions: ["fetch_forecast", "parse_response"] },
      world_state: { branch: "main", api_calls_count: 3, active_tools: ["weather_api"], error_count: 1 },
      agent: { id: "demo-agent", session_id: "sess-a8f3", uptime_ms: 480000 },
    },
    "a1c2d3e4ff556677": {
      memory: { last_action: "user_input", response_text: null, tokens_used: 512, pending_actions: ["process_input"] },
      world_state: { branch: "main", api_calls_count: 1, active_tools: [], error_count: 0 },
      agent: { id: "demo-agent", session_id: "sess-a8f3", uptime_ms: 360000 },
    },
    "7788aabb11223344": {
      memory: { last_action: "checkpoint", response_text: null, tokens_used: 128 },
      world_state: { branch: "main", api_calls_count: 0, active_tools: [], error_count: 0 },
      agent: { id: "demo-agent", session_id: "sess-a8f3", uptime_ms: 120000 },
    },
    "dd22ee33ff445566": {
      memory: { last_action: "checkpoint", response_text: null, tokens_used: 0 },
      world_state: { branch: "main", api_calls_count: 0, active_tools: [], error_count: 0 },
      agent: { id: "demo-agent", session_id: "sess-a8f3", uptime_ms: 0 },
    },
  };
  return states[hash] || {
    memory: { last_action: "unknown", tokens_used: 0 },
    world_state: { branch: "unknown" },
    agent: { id: "unknown" },
  };
}

// ---------------------------------------------------------------------------
// Demo replay timeline
// ---------------------------------------------------------------------------
export function getDemoReplayTimeline(): ReplayStep[] {
  const data = makeDemoData();
  const mainCommits = data.commits
    .filter((c) => c.branch === "main")
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

  return mainCommits.map((commit) => ({
    commit,
    state: getDemoCommitState(commit.hash),
  }));
}
