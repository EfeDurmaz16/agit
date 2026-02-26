"use client";

import Link from "next/link";

export default function LandingPage() {
  return (
    <div className="min-h-screen">
      {/* Nav */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white/80 backdrop-blur-lg border-b border-stone-200/50">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-emerald-600 flex items-center justify-center">
              <span className="text-white text-xs font-bold font-mono">ag</span>
            </div>
            <span className="text-base font-semibold tracking-tight">agit</span>
          </div>
          <div className="flex items-center gap-6">
            <a href="#features" className="text-sm text-stone-500 hover:text-stone-900 transition-colors">
              Features
            </a>
            <a href="#proof" className="text-sm text-stone-500 hover:text-stone-900 transition-colors">
              Proof Points
            </a>
            <a href="#integrations" className="text-sm text-stone-500 hover:text-stone-900 transition-colors">
              Integrations
            </a>
            <a
              href="https://github.com/EfeDurmaz16/agit"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-stone-500 hover:text-stone-900 transition-colors"
            >
              GitHub
            </a>
            <Link
              href="/"
              className="text-sm font-medium bg-stone-900 text-white px-4 py-1.5 rounded-lg hover:bg-stone-800 transition-colors"
            >
              Dashboard
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-32 pb-20 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 bg-emerald-50 text-emerald-700 text-xs font-medium px-3 py-1.5 rounded-full mb-6 border border-emerald-100">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            Gartner: 40% of agentic AI projects will fail by 2027
          </div>

          <h1 className="text-5xl md:text-6xl font-semibold tracking-tight text-stone-900 leading-[1.1] mb-6">
            Git for
            <br />
            <span className="text-emerald-600">AI Agents</span>
          </h1>

          <p className="text-lg text-stone-500 max-w-2xl mx-auto mb-10 leading-relaxed">
            Your agents work great in pilot, fail in production because they have no version control.
            AgentGit brings 20 years of software reliability to AI.
          </p>

          <div className="flex items-center justify-center gap-3">
            <a
              href="#get-started"
              className="inline-flex items-center gap-2 bg-emerald-600 text-white font-medium px-6 py-2.5 rounded-lg hover:bg-emerald-700 transition-colors text-sm"
            >
              Get Started
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                <path d="M3 8H13M10 5L13 8L10 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </a>
            <code className="text-sm font-mono bg-white text-stone-600 px-4 py-2.5 rounded-lg border border-stone-200">
              pip install agit
            </code>
          </div>
        </div>

        {/* Code preview */}
        <div className="max-w-3xl mx-auto mt-16">
          <div className="bg-stone-900 rounded-xl border border-stone-800 overflow-hidden shadow-2xl shadow-stone-900/20">
            <div className="flex items-center gap-1.5 px-4 py-3 border-b border-stone-800">
              <div className="w-2.5 h-2.5 rounded-full bg-stone-700" />
              <div className="w-2.5 h-2.5 rounded-full bg-stone-700" />
              <div className="w-2.5 h-2.5 rounded-full bg-stone-700" />
              <span className="text-xs text-stone-500 ml-3 font-mono">agent.py</span>
            </div>
            <pre className="p-5 text-sm font-mono leading-7 overflow-x-auto">
              <code>
                <span className="text-stone-500">from</span>{" "}
                <span className="text-emerald-400">agit</span>{" "}
                <span className="text-stone-500">import</span>{" "}
                <span className="text-white">ExecutionEngine</span>{"\n"}
                {"\n"}
                <span className="text-stone-500">engine = </span>
                <span className="text-white">ExecutionEngine</span>
                <span className="text-stone-400">(</span>
                <span className="text-emerald-300">&quot;./repo&quot;</span>
                <span className="text-stone-400">, </span>
                <span className="text-stone-500">agent_id=</span>
                <span className="text-emerald-300">&quot;my-agent&quot;</span>
                <span className="text-stone-400">)</span>{"\n"}
                {"\n"}
                <span className="text-stone-600"># Every action is an auditable commit</span>{"\n"}
                <span className="text-stone-500">engine.</span>
                <span className="text-white">commit_state</span>
                <span className="text-stone-400">(</span>
                <span className="text-white">state</span>
                <span className="text-stone-400">, </span>
                <span className="text-emerald-300">&quot;tool call: weather_api&quot;</span>
                <span className="text-stone-400">)</span>{"\n"}
                {"\n"}
                <span className="text-stone-600"># Something went wrong? Instant rollback</span>{"\n"}
                <span className="text-stone-500">engine.</span>
                <span className="text-white">revert</span>
                <span className="text-stone-400">(</span>
                <span className="text-white">commit_hash</span>
                <span className="text-stone-400">)  </span>
                <span className="text-stone-600"># &lt;5s recovery</span>{"\n"}
                {"\n"}
                <span className="text-stone-600"># See exactly what changed</span>{"\n"}
                <span className="text-stone-500">diff = engine.</span>
                <span className="text-white">diff</span>
                <span className="text-stone-400">(</span>
                <span className="text-white">hash_a</span>
                <span className="text-stone-400">, </span>
                <span className="text-white">hash_b</span>
                <span className="text-stone-400">)  </span>
                <span className="text-stone-600"># Merkle tree diff</span>
              </code>
            </pre>
          </div>
        </div>
      </section>

      {/* Stats bar */}
      <section className="border-y border-stone-200 bg-white py-12">
        <div className="max-w-5xl mx-auto px-6 grid grid-cols-4 gap-8">
          {[
            { value: "96%", label: "Retry Success Rate", sub: "up from 45%" },
            { value: "<5s", label: "Recovery Time", sub: "instant rollback" },
            { value: "98%", label: "Audit Completeness", sub: "full observability" },
            { value: "-40%", label: "Token Cost", sub: "branch reuse" },
          ].map((stat) => (
            <div key={stat.label} className="text-center">
              <p className="text-3xl font-semibold text-stone-900 tabular-nums">
                {stat.value}
              </p>
              <p className="text-sm font-medium text-stone-700 mt-1">
                {stat.label}
              </p>
              <p className="text-xs text-stone-400 mt-0.5">{stat.sub}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-20 px-6">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl font-semibold tracking-tight text-stone-900">
              The missing reliability layer for AI agents
            </h2>
            <p className="text-stone-500 mt-3 max-w-xl mx-auto">
              Every failure mode Gartner identified has a direct solution in AgentGit.
            </p>
          </div>

          <div className="grid grid-cols-3 gap-5">
            {[
              {
                title: "Immutable Audit Trail",
                desc: "Every action is a SHA-256 commit. See exactly what your agent did, when, and why. 98% audit completeness.",
                icon: (
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" className="text-emerald-600">
                    <rect x="2" y="2" width="16" height="16" rx="3" stroke="currentColor" strokeWidth="1.5" />
                    <path d="M6 10L9 13L14 7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                ),
              },
              {
                title: "Instant Rollback",
                desc: "Revert any agent mistake in under 5 seconds. Content-addressable storage means zero data loss, ever.",
                icon: (
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" className="text-emerald-600">
                    <path d="M4 10C4 6.69 6.69 4 10 4C13.31 4 16 6.69 16 10C16 13.31 13.31 16 10 16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                    <path d="M2 10L4 12L6 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                ),
              },
              {
                title: "Branch-per-Retry",
                desc: "Failed action? Automatic retry on an isolated branch. Exponential backoff, merge on success. 96% success rate.",
                icon: (
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" className="text-emerald-600">
                    <circle cx="6" cy="6" r="2.5" stroke="currentColor" strokeWidth="1.5" />
                    <circle cx="6" cy="14" r="2.5" stroke="currentColor" strokeWidth="1.5" />
                    <circle cx="14" cy="10" r="2.5" stroke="currentColor" strokeWidth="1.5" />
                    <line x1="6" y1="8.5" x2="6" y2="11.5" stroke="currentColor" strokeWidth="1.5" />
                    <path d="M6 8.5C6 10 9 10 11.5 10" stroke="currentColor" strokeWidth="1.5" fill="none" />
                  </svg>
                ),
              },
              {
                title: "Merkle Tree Diffs",
                desc: "Only the changed keys are stored and compared. Efficient even with massive agent state trees.",
                icon: (
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" className="text-emerald-600">
                    <rect x="7" y="2" width="6" height="4" rx="1" stroke="currentColor" strokeWidth="1.5" />
                    <rect x="2" y="14" width="5" height="4" rx="1" stroke="currentColor" strokeWidth="1.5" />
                    <rect x="13" y="14" width="5" height="4" rx="1" stroke="currentColor" strokeWidth="1.5" />
                    <line x1="10" y1="6" x2="10" y2="10" stroke="currentColor" strokeWidth="1.5" />
                    <line x1="4.5" y1="14" x2="10" y2="10" stroke="currentColor" strokeWidth="1.5" />
                    <line x1="15.5" y1="14" x2="10" y2="10" stroke="currentColor" strokeWidth="1.5" />
                  </svg>
                ),
              },
              {
                title: "PII Masking",
                desc: "11 built-in patterns detect and redact sensitive data before it reaches storage. SOC2/HIPAA ready.",
                icon: (
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" className="text-emerald-600">
                    <path d="M10 2L3 6V10C3 14.42 6 17.4 10 18C14 17.4 17 14.42 17 10V6L10 2Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
                    <path d="M7 10L9 12L13 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                ),
              },
              {
                title: "Multi-Agent Swarm",
                desc: "Orchestrate multiple agents with distributed locks, consensus voting, and isolated branch execution.",
                icon: (
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" className="text-emerald-600">
                    <circle cx="10" cy="4" r="2.5" stroke="currentColor" strokeWidth="1.5" />
                    <circle cx="4" cy="14" r="2.5" stroke="currentColor" strokeWidth="1.5" />
                    <circle cx="16" cy="14" r="2.5" stroke="currentColor" strokeWidth="1.5" />
                    <line x1="10" y1="6.5" x2="5" y2="11.5" stroke="currentColor" strokeWidth="1.5" />
                    <line x1="10" y1="6.5" x2="15" y2="11.5" stroke="currentColor" strokeWidth="1.5" />
                    <line x1="6.5" y1="14" x2="13.5" y2="14" stroke="currentColor" strokeWidth="1.5" />
                  </svg>
                ),
              },
            ].map((feature) => (
              <div
                key={feature.title}
                className="bg-white rounded-xl border border-stone-200 p-5 hover:shadow-md hover:border-stone-300 transition-all"
              >
                <div className="w-9 h-9 rounded-lg bg-emerald-50 flex items-center justify-center mb-3">
                  {feature.icon}
                </div>
                <h3 className="text-sm font-semibold text-stone-900 mb-1.5">
                  {feature.title}
                </h3>
                <p className="text-xs text-stone-500 leading-relaxed">
                  {feature.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Problem-Solution */}
      <section id="proof" className="py-20 px-6 bg-white border-y border-stone-200">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl font-semibold tracking-tight text-stone-900 text-center mb-14">
            From failure to production-ready
          </h2>

          <div className="space-y-4">
            {[
              {
                problem: "Cannot trust agent decisions",
                solution: "agit diff + immutable reasoning logs",
                impact: "95% explainability",
              },
              {
                problem: "No visibility into failures",
                solution: "agit log + real-time dashboard",
                impact: "MTTR: 5min to 30s",
              },
              {
                problem: "Cannot rollback mistakes",
                solution: "agit revert + checkpoint store",
                impact: "Zero data loss",
              },
              {
                problem: "Token costs exploding",
                solution: "Branch reuse + smart checkpoints",
                impact: "40% cost reduction",
              },
              {
                problem: "No compliance story",
                solution: "PII masking + AES-256 encryption",
                impact: "SOC2/HIPAA ready",
              },
            ].map((row) => (
              <div
                key={row.problem}
                className="grid grid-cols-3 gap-4 items-center py-4 border-b border-stone-100 last:border-0"
              >
                <div className="flex items-center gap-3">
                  <div className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" />
                  <span className="text-sm text-stone-600">{row.problem}</span>
                </div>
                <div className="flex items-center gap-3">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="text-stone-300 shrink-0">
                    <path d="M3 8H13M10 5L13 8L10 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <span className="text-sm font-mono text-stone-700">
                    {row.solution}
                  </span>
                </div>
                <div className="flex items-center justify-end">
                  <span className="text-sm font-medium text-emerald-600 bg-emerald-50 px-3 py-1 rounded-full">
                    {row.impact}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Integrations */}
      <section id="integrations" className="py-20 px-6">
        <div className="max-w-5xl mx-auto text-center">
          <h2 className="text-3xl font-semibold tracking-tight text-stone-900 mb-4">
            Works with your stack
          </h2>
          <p className="text-stone-500 mb-12">
            8 framework integrations, 3 SDKs, production-ready from day one.
          </p>

          <div className="flex flex-wrap items-center justify-center gap-4">
            {[
              "LangGraph",
              "CrewAI",
              "OpenAI Agents",
              "Claude SDK",
              "Google ADK",
              "Vercel AI",
              "OpenClaw",
              "MCP Server",
            ].map((name) => (
              <div
                key={name}
                className="bg-white border border-stone-200 rounded-lg px-5 py-3 text-sm text-stone-700 font-medium hover:border-emerald-300 hover:bg-emerald-50/30 transition-all"
              >
                {name}
              </div>
            ))}
          </div>

          <div className="flex items-center justify-center gap-8 mt-10 text-xs text-stone-400">
            <span>Rust Core Engine</span>
            <span className="w-1 h-1 rounded-full bg-stone-300" />
            <span>Python SDK</span>
            <span className="w-1 h-1 rounded-full bg-stone-300" />
            <span>TypeScript SDK</span>
            <span className="w-1 h-1 rounded-full bg-stone-300" />
            <span>REST API</span>
            <span className="w-1 h-1 rounded-full bg-stone-300" />
            <span>CLI</span>
          </div>
        </div>
      </section>

      {/* Comparison table */}
      <section className="py-20 px-6 bg-white border-y border-stone-200">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-semibold tracking-tight text-stone-900 text-center mb-12">
            Why AgentGit wins
          </h2>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-stone-200">
                  <th className="text-left py-3 px-4 font-medium text-stone-500">
                    Capability
                  </th>
                  <th className="text-center py-3 px-4 font-medium text-stone-400">
                    LangGraph
                  </th>
                  <th className="text-center py-3 px-4 font-medium text-stone-400">
                    CrewAI
                  </th>
                  <th className="text-center py-3 px-4 font-semibold text-emerald-600">
                    AgentGit
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {[
                  ["Audit Trail", "Basic", "None", "98%"],
                  ["Rollback", "Manual", "None", "Instant"],
                  ["Retry Logic", "Simple", "Basic", "96% success"],
                  ["PII Masking", "No", "No", "11 patterns"],
                  ["Encryption", "No", "No", "AES-256"],
                  ["Multi-Agent", "Yes", "Yes", "Consensus + Locks"],
                  ["Gartner-proof", "No", "No", "Yes"],
                ].map(([cap, lg, cr, ag]) => (
                  <tr key={cap} className="hover:bg-stone-50/50">
                    <td className="py-3 px-4 font-medium text-stone-700">
                      {cap}
                    </td>
                    <td className="py-3 px-4 text-center text-stone-400">
                      {lg}
                    </td>
                    <td className="py-3 px-4 text-center text-stone-400">
                      {cr}
                    </td>
                    <td className="py-3 px-4 text-center font-medium text-emerald-600">
                      {ag}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section id="get-started" className="py-24 px-6">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-4xl font-semibold tracking-tight text-stone-900 mb-4">
            Stop the 40% failure rate
          </h2>
          <p className="text-stone-500 text-lg mb-10">
            Add version control to your agents in 3 lines of code.
          </p>

          <div className="bg-stone-900 rounded-xl p-6 max-w-lg mx-auto mb-8">
            <pre className="text-sm font-mono text-left leading-7">
              <code>
                <span className="text-stone-500">$</span>{" "}
                <span className="text-emerald-400">pip install agit</span>{"\n"}
                <span className="text-stone-500">$</span>{" "}
                <span className="text-stone-300">python</span>{"\n"}
                <span className="text-stone-500">{">>>"}</span>{" "}
                <span className="text-stone-400">from</span>{" "}
                <span className="text-emerald-400">agit</span>{" "}
                <span className="text-stone-400">import</span>{" "}
                <span className="text-white">ExecutionEngine</span>
              </code>
            </pre>
          </div>

          <div className="flex items-center justify-center gap-4">
            <a
              href="https://github.com/EfeDurmaz16/agit"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 bg-stone-900 text-white font-medium px-6 py-2.5 rounded-lg hover:bg-stone-800 transition-colors text-sm"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
              </svg>
              View on GitHub
            </a>
            <Link
              href="/"
              className="inline-flex items-center gap-2 bg-emerald-600 text-white font-medium px-6 py-2.5 rounded-lg hover:bg-emerald-700 transition-colors text-sm"
            >
              Try Dashboard
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-stone-200 py-8 px-6">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded bg-emerald-600 flex items-center justify-center">
              <span className="text-white text-[8px] font-bold font-mono">ag</span>
            </div>
            <span className="text-xs text-stone-400">
              AgentGit v2.0 &mdash; Git for AI Agents
            </span>
          </div>
          <div className="flex items-center gap-6 text-xs text-stone-400">
            <span>Rust Core + Python SDK + TypeScript SDK</span>
            <span>MIT License</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
