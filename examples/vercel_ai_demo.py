#!/usr/bin/env python3
"""Vercel AI SDK + agit integration demo.

Demonstrates using AgitVercelMiddleware for automatic
versioning of AI SDK interactions.

Usage:
    pip install agit[vercel]
    python examples/vercel_ai_demo.py
"""
from __future__ import annotations


def main():
    """Run the Vercel AI + agit demo."""
    try:
        from agit.integrations.vercel_ai import AgitVercelMiddleware
    except ImportError:
        print("Vercel AI integration not available.")
        print("Install with: pip install agit[vercel]")
        return

    print("=== Vercel AI SDK + agit Demo ===\n")

    # Create middleware instance
    middleware = AgitVercelMiddleware(repo_path="/tmp/agit-vercel-demo")
    print("Created AgitVercelMiddleware\n")

    # Simulate sync usage
    print("--- Sync Example ---")
    mock_params = {
        "model": "gpt-4",
        "prompt": "Explain quantum computing",
    }
    print(f"  Request: {mock_params['prompt'][:50]}")

    try:
        result = middleware.on_generate(mock_params)
        print(f"  Middleware captured request: {result is not None}")
    except Exception as e:
        print(f"  (noted: {e})")

    # Simulate streaming scenario
    print("\n--- Streaming Example ---")
    stream_params = {
        "model": "gpt-4",
        "prompt": "Write a haiku about AI",
        "stream": True,
    }
    print(f"  Streaming request: {stream_params['prompt']}")

    try:
        result = middleware.on_stream(stream_params)
        print(f"  Stream middleware active: {result is not None}")
    except Exception as e:
        print(f"  (noted: {e})")

    # Error handling demo
    print("\n--- Error Handling ---")
    try:
        middleware.on_error({"error": "API timeout", "retry": True})
        print("  Error recorded in agit history")
    except Exception as e:
        print(f"  (noted: {e})")

    print("\n=== Demo Complete ===")
    print("agit middleware automatically versions all Vercel AI SDK interactions.")


if __name__ == "__main__":
    main()
