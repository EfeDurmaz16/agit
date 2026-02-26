#!/usr/bin/env python3
"""Static contract checks across Rust/Python/TypeScript surfaces.

This script prevents silent API/SDK drift in CI by validating critical
cross-language interface invariants from source files.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent.parent


def read(rel: str) -> str:
    p = ROOT / rel
    if not p.exists():
        raise AssertionError(f"Missing file: {rel}")
    return p.read_text(encoding="utf-8")


def require(pattern: str, content: str, context: str) -> None:
    if not re.search(pattern, content, re.MULTILINE | re.DOTALL):
        raise AssertionError(f"Contract check failed: {context}")


def main() -> int:
    ts_client = read("ts-sdk/src/client.ts")
    rust_repo = read("crates/agit-node/src/repository.rs")
    py_models = read("python/agit/server/models.py")
    web_api = read("web/src/lib/api.ts")

    # TS SDK <-> Rust NAPI commit payload contract
    require(
        r"interface\s+NativeRepository\s*\{[\s\S]*commit\(\s*memory_json:\s*string,\s*world_state_json:\s*string,",
        ts_client,
        "TS NativeRepository.commit must use JSON string args",
    )
    require(
        r"pub\s+async\s+fn\s+commit\(\s*&self,\s*memory_json:\s*String,\s*world_state_json:\s*String,[\s\S]*metadata_json:\s*Option<String>",
        rust_repo,
        "Rust JsRepository.commit must accept metadata_json",
    )

    # REST branches contract: server returns map, web maps to Branch[]
    require(
        r"class\s+BranchList\(BaseModel\):[\s\S]*branches:\s*dict\[str,\s*str\]",
        py_models,
        "Python BranchList.branches must be a map",
    )
    require(
        r"interface\s+BranchListResponse\s*\{[\s\S]*branches:\s*Record<string,\s*string>;",
        web_api,
        "Web BranchListResponse must model server map response",
    )
    require(
        r"Object\.entries\(data\.branches",
        web_api,
        "Web getBranches must transform map response to Branch[]",
    )

    # Web API key propagation contract
    require(
        r"headers\[\"X-API-Key\"\]\s*=\s*API_KEY",
        web_api,
        "Web fetchApi must forward X-API-Key when configured",
    )

    print("Contract checks passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
