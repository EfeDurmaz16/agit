/**
 * Integration tests for AgitClient (using the pure-TS fallback).
 *
 * These tests run entirely in-memory via `forcePureTs: true`, so no compiled
 * native binary is required.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { AgitClient } from "../src/client.js";
import { ActionType, ChangeType, MergeStrategy } from "../src/types.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function openRepo(): Promise<AgitClient> {
  return AgitClient.open("/tmp/agit-test", { forcePureTs: true });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AgitClient (pure-TS fallback)", () => {
  let client: AgitClient;

  beforeEach(async () => {
    client = await openRepo();
  });

  // ---- status / init -------------------------------------------------------

  it("has no commits on init", () => {
    const s = client.status();
    expect(s.head).toBeNull();
    expect(s.current_branch).toBe("main");
    expect(s.branches).toEqual([]);
  });

  // ---- commit --------------------------------------------------------------

  it("creates a commit and returns a hash", async () => {
    const hash = await client.commit({
      memory: { step: 1 },
      message: "first",
    });
    expect(typeof hash).toBe("string");
    expect(hash.length).toBeGreaterThan(0);
  });

  it("HEAD advances after each commit", async () => {
    await client.commit({ memory: { n: 1 }, message: "one" });
    const s1 = client.status();
    await client.commit({ memory: { n: 2 }, message: "two" });
    const s2 = client.status();
    expect(s2.head).not.toBe(s1.head);
    expect(s2.head).not.toBeNull();
  });

  it("stores world_state and metadata", async () => {
    const hash = await client.commit({
      memory: { x: 42 },
      world_state: { env: "prod" },
      message: "with world state",
      cost: 0.001,
      metadata: { run_id: "abc" },
    });
    const state = await client.getState(hash);
    expect(state.memory).toEqual({ x: 42 });
    expect(state.world_state).toEqual({ env: "prod" });
    expect(state.cost).toBeCloseTo(0.001);
  });

  it("respects action_type", async () => {
    const hash = await client.commit({
      memory: {},
      message: "tool call",
      action_type: ActionType.ToolCall,
    });
    const log = await client.log({ limit: 1 });
    expect(log[0].hash).toBe(hash);
    expect(log[0].action_type).toBe(ActionType.ToolCall);
  });

  // ---- log -----------------------------------------------------------------

  it("returns commits in reverse chronological order", async () => {
    await client.commit({ memory: { n: 1 }, message: "a" });
    await client.commit({ memory: { n: 2 }, message: "b" });
    await client.commit({ memory: { n: 3 }, message: "c" });

    const log = await client.log();
    expect(log.length).toBe(3);
    // Most recent first
    expect(log[0].message).toBe("c");
    expect(log[2].message).toBe("a");
  });

  it("respects the limit option", async () => {
    for (let i = 0; i < 5; i++) {
      await client.commit({ memory: { i }, message: `commit ${i}` });
    }
    const log = await client.log({ limit: 3 });
    expect(log.length).toBe(3);
  });

  // ---- getState ------------------------------------------------------------

  it("retrieves state by commit hash", async () => {
    const hash = await client.commit({
      memory: { data: "hello" },
      world_state: { world: true },
      message: "test",
    });
    const state = await client.getState(hash);
    expect(state.memory).toEqual({ data: "hello" });
    expect(state.world_state).toEqual({ world: true });
  });

  it("throws when hash is unknown", async () => {
    await expect(client.getState("deadbeef")).rejects.toThrow();
  });

  // ---- branch --------------------------------------------------------------

  it("creates a branch and lists it", async () => {
    await client.commit({ memory: { v: 1 }, message: "base" });
    await client.branch({ name: "feature" });
    const s = client.status();
    expect(s.branches).toContain("main");
    expect(s.branches).toContain("feature");
  });

  it("creates a branch from a specific hash", async () => {
    const h1 = await client.commit({ memory: { v: 1 }, message: "one" });
    await client.commit({ memory: { v: 2 }, message: "two" });
    await client.branch({ name: "from-one", from: h1 });
    const state = await client.checkout("from-one");
    expect(state.memory).toEqual({ v: 1 });
  });

  // ---- checkout ------------------------------------------------------------

  it("checks out a branch and updates current_branch", async () => {
    await client.commit({ memory: { v: 1 }, message: "base" });
    await client.branch({ name: "feat" });
    await client.checkout("feat");
    const s = client.status();
    expect(s.current_branch).toBe("feat");
  });

  it("returns the state at the checked-out point", async () => {
    await client.commit({ memory: { v: 1 }, message: "base" });
    await client.branch({ name: "feat" });
    const state = await client.checkout("feat");
    expect(state.memory).toEqual({ v: 1 });
  });

  it("can checkout by commit hash (detached HEAD)", async () => {
    const h1 = await client.commit({ memory: { v: 1 }, message: "one" });
    await client.commit({ memory: { v: 2 }, message: "two" });
    const state = await client.checkout(h1);
    expect(state.memory).toEqual({ v: 1 });
    expect(client.status().current_branch).toBeNull();
  });

  it("throws when checking out unknown ref", async () => {
    await expect(client.checkout("no-such-branch")).rejects.toThrow();
  });

  // ---- diff ----------------------------------------------------------------

  it("diffs two commits", async () => {
    const h1 = await client.commit({
      memory: { a: 1, b: 2 },
      message: "first",
    });
    const h2 = await client.commit({
      memory: { a: 1, b: 3, c: 4 },
      message: "second",
    });

    const diff = await client.diff(h1, h2);
    expect(diff.base_hash).toBe(h1);
    expect(diff.target_hash).toBe(h2);
    expect(diff.entries.length).toBeGreaterThan(0);

    const paths = diff.entries.map((e) => e.path.join("."));
    // b changed
    expect(paths.some((p) => p.includes("b"))).toBe(true);
  });

  it("returns no diff entries for identical states", async () => {
    const h1 = await client.commit({ memory: { x: 1 }, message: "a" });
    const h2 = await client.commit({ memory: { x: 1 }, message: "b" });
    const diff = await client.diff(h1, h2);
    // Memory is identical so the memory subtree should show no change.
    const memoryEntries = diff.entries.filter((e) =>
      e.path.join(".").startsWith("memory")
    );
    expect(memoryEntries.length).toBe(0);
  });

  it("identifies added and removed keys", async () => {
    const h1 = await client.commit({ memory: { a: 1 }, message: "one" });
    const h2 = await client.commit({
      memory: { b: 2 },
      message: "two",
    });
    const diff = await client.diff(h1, h2);
    const changeTypes = diff.entries.map((e) => e.change_type);
    expect(changeTypes).toContain(ChangeType.Added);
    expect(changeTypes).toContain(ChangeType.Removed);
  });

  // ---- revert --------------------------------------------------------------

  it("reverts to a previous state", async () => {
    const h1 = await client.commit({ memory: { v: 1 }, message: "one" });
    await client.commit({ memory: { v: 2 }, message: "two" });

    const reverted = await client.revert(h1);
    expect(reverted.memory).toEqual({ v: 1 });

    // Should now have 3 commits
    const log = await client.log();
    expect(log.length).toBe(3);
    expect(log[0].action_type).toBe(ActionType.Rollback);
  });

  it("throws when reverting to unknown hash", async () => {
    await expect(client.revert("unknown")).rejects.toThrow();
  });

  // ---- merge ---------------------------------------------------------------

  it("merges with Ours strategy keeps current branch state", async () => {
    // Base
    await client.commit({ memory: { v: 0 }, message: "base" });

    // Create feature branch
    await client.branch({ name: "feature" });
    await client.checkout("feature");
    await client.commit({ memory: { v: 2 }, message: "feature work" });

    // Back to main
    await client.checkout("main");
    await client.commit({ memory: { v: 1 }, message: "main work" });

    const hash = await client.merge({
      branch: "feature",
      strategy: MergeStrategy.Ours,
    });
    const merged = await client.getState(hash);
    expect(merged.memory).toEqual({ v: 1 }); // ours
  });

  it("merges with Theirs strategy takes incoming state", async () => {
    await client.commit({ memory: { v: 0 }, message: "base" });
    await client.branch({ name: "incoming" });
    await client.checkout("incoming");
    await client.commit({ memory: { v: 99 }, message: "incoming work" });

    await client.checkout("main");
    await client.commit({ memory: { v: 1 }, message: "main work" });

    const hash = await client.merge({
      branch: "incoming",
      strategy: MergeStrategy.Theirs,
    });
    const merged = await client.getState(hash);
    expect(merged.memory).toEqual({ v: 99 }); // theirs
  });

  it("throws when merging a non-existent branch", async () => {
    await client.commit({ memory: {}, message: "base" });
    await expect(
      client.merge({ branch: "ghost" })
    ).rejects.toThrow();
  });

  // ---- status --------------------------------------------------------------

  it("status reflects current HEAD and branch", async () => {
    const h = await client.commit({ memory: {}, message: "init" });
    const s = client.status();
    expect(s.head).toBe(h);
    expect(s.current_branch).toBe("main");
    expect(s.branches).toContain("main");
  });
});
