"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getDemoData, api } from "@/lib/api";
import { truncateHash, relativeTime } from "@/lib/utils";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

const actionTypeColor: Record<string, string> = {
  user_input: "bg-stone-400",
  tool_call: "bg-emerald-500",
  llm_response: "bg-emerald-300",
  checkpoint: "bg-stone-300",
  rollback: "bg-red-400",
  system_event: "bg-amber-400",
};

const actionBadgeVariant = (action: string) => {
  if (action === "tool_call" || action === "llm_response") return "emerald" as const;
  if (action === "rollback") return "destructive" as const;
  if (action === "checkpoint") return "outline" as const;
  return "default" as const;
};

// Generate chart data from commits
function buildChartData() {
  const now = Date.now();
  const points = [];
  for (let i = 11; i >= 0; i--) {
    const t = new Date(now - i * 60000 * 2);
    points.push({
      time: t.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }),
      commits: Math.max(0, Math.floor(Math.random() * 4) + (i < 4 ? 2 : 0)),
      actions: Math.max(0, Math.floor(Math.random() * 6) + (i < 4 ? 3 : 1)),
    });
  }
  return points;
}

export default function DashboardPage() {
  const data = getDemoData();
  const commits = data.commits;
  const branches = data.branches;
  const agents = [...new Set(commits.map((c) => c.author))];
  const chartData = buildChartData();

  const [apiConnected, setApiConnected] = useState<boolean | null>(null);

  useEffect(() => {
    api.getHealth()
      .then(() => setApiConnected(true))
      .catch(() => setApiConnected(false));
  }, []);

  return (
    <div>
      {/* Header */}
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-stone-900">
            Dashboard
          </h1>
          <p className="text-sm text-stone-500 mt-1">
            Agent version control overview
          </p>
        </div>
        <div className="flex items-center gap-2 mt-1">
          <span
            className={`w-2 h-2 rounded-full ${
              apiConnected === null
                ? "bg-stone-300"
                : apiConnected
                ? "bg-emerald-500"
                : "bg-red-500"
            }`}
          />
          <span className="text-xs text-stone-500">
            {apiConnected === null
              ? "Checking..."
              : apiConnected
              ? "Connected"
              : "Disconnected"}
          </span>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <MetricCard
          label="Total Commits"
          value={commits.length.toString()}
          change="+3 today"
          positive
        />
        <MetricCard
          label="Active Branches"
          value={branches.length.toString()}
          change="1 main"
        />
        <MetricCard
          label="Agents"
          value={agents.length.toString()}
          change="all healthy"
          positive
        />
        <MetricCard
          label="Retry Success"
          value="96%"
          change="+2% this week"
          positive
        />
      </div>

      {/* Chart + Activity */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        {/* Chart */}
        <Card className="col-span-2">
          <CardHeader>
            <CardTitle>Activity</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="emeraldGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#10b981" stopOpacity={0.15} />
                      <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="stoneGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#78716c" stopOpacity={0.1} />
                      <stop offset="100%" stopColor="#78716c" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="time"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fontSize: 11, fill: "#a8a29e" }}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fontSize: 11, fill: "#a8a29e" }}
                    width={28}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#1c1917",
                      border: "none",
                      borderRadius: "8px",
                      color: "#fff",
                      fontSize: "12px",
                      padding: "8px 12px",
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="actions"
                    stroke="#a8a29e"
                    strokeWidth={1.5}
                    fill="url(#stoneGrad)"
                  />
                  <Area
                    type="monotone"
                    dataKey="commits"
                    stroke="#10b981"
                    strokeWidth={2}
                    fill="url(#emeraldGrad)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Action breakdown */}
        <Card>
          <CardHeader>
            <CardTitle>Action Types</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {Object.entries(
                commits.reduce<Record<string, number>>((acc, c) => {
                  acc[c.action_type] = (acc[c.action_type] || 0) + 1;
                  return acc;
                }, {})
              )
                .sort(([, a], [, b]) => b - a)
                .map(([action, count]) => (
                  <div key={action} className="flex items-center gap-3">
                    <div
                      className={`w-2 h-2 rounded-full ${actionTypeColor[action] || "bg-stone-300"}`}
                    />
                    <span className="text-sm text-stone-600 flex-1 font-mono">
                      {action}
                    </span>
                    <span className="text-sm font-medium text-stone-900 tabular-nums">
                      {count}
                    </span>
                  </div>
                ))}
            </div>
            <div className="mt-5 pt-4 border-t border-stone-100">
              <div className="flex items-center justify-between text-xs text-stone-400">
                <span>Total</span>
                <span className="font-medium text-stone-600">{commits.length}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recent Activity */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Activity</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="divide-y divide-stone-100">
            {commits.map((commit) => (
              <div
                key={commit.hash}
                className="flex items-center gap-4 py-3 first:pt-0 last:pb-0"
              >
                <div
                  className={`w-2 h-2 rounded-full shrink-0 ${actionTypeColor[commit.action_type] || "bg-stone-300"}`}
                />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-stone-800 truncate">
                    {commit.message}
                  </p>
                  <p className="text-xs text-stone-400 mt-0.5">
                    {commit.author}
                  </p>
                </div>
                <Badge variant={actionBadgeVariant(commit.action_type)}>
                  {commit.action_type}
                </Badge>
                <code className="text-xs font-mono text-stone-400 shrink-0">
                  {truncateHash(commit.hash)}
                </code>
                <span className="text-xs text-stone-400 shrink-0 w-16 text-right">
                  {relativeTime(commit.timestamp)}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function MetricCard({
  label,
  value,
  change,
  positive,
}: {
  label: string;
  value: string;
  change: string;
  positive?: boolean;
}) {
  return (
    <Card>
      <CardContent className="pt-5">
        <p className="text-xs font-medium text-stone-400 uppercase tracking-wider">
          {label}
        </p>
        <p className="text-3xl font-semibold text-stone-900 mt-1.5 tabular-nums">
          {value}
        </p>
        <p
          className={`text-xs mt-1.5 ${positive ? "text-emerald-600" : "text-stone-400"}`}
        >
          {change}
        </p>
      </CardContent>
    </Card>
  );
}
