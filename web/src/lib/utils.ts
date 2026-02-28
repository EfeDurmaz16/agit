import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function truncateHash(hash: string, len = 8): string {
  return hash.slice(0, len);
}

export function relativeTime(timestamp: string): string {
  const now = Date.now();
  const then = new Date(timestamp).getTime();
  const diff = now - then;

  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(timestamp).toLocaleDateString();
}

export function formatTimestamp(timestamp: string): string {
  return new Date(timestamp).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function actionTypeColor(actionType: string): string {
  switch (actionType) {
    case "tool_call": return "#5B8DEF";
    case "llm_response": return "#4ADE80";
    case "rollback": return "#E85D5D";
    case "checkpoint": return "#E8A44A";
    case "user_input": return "#6E6E76";
    default: return "#6E6E76";
  }
}

export function levelColor(level: string): string {
  switch (level) {
    case "info": return "#6E6E76";
    case "warning": return "#E8A44A";
    case "error": return "#E85D5D";
    default: return "#6E6E76";
  }
}

export function downloadAsJson(data: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
