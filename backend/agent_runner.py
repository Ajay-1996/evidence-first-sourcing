"""The one agent loop every step shares.

An "agent" here is exactly three things:
  1. a markdown file in agents/<name>.md   — its behaviour (edit it, behaviour changes)
  2. an entry in models.yaml               — which provider/model runs it
  3. a dict of python tools                — the only way it touches data or does arithmetic

run_agent() loads (1) and (2) fresh on every call — changing the MD or the yaml requires no
restart — then loops: model → tool calls → tool results → model … until the model stops
calling tools. Every step lands in an AgentTrace so the UI can show the working.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import yaml

from .providers import get_provider
from .schemas import AgentTrace

ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT / "agents"
MODELS_YAML = ROOT / "models.yaml"

MAX_LOOPS = 40


def load_agent_config(agent: str) -> dict[str, Any]:
    import os
    cfg = yaml.safe_load(MODELS_YAML.read_text())
    merged = dict(cfg.get("defaults", {}))
    merged.update(cfg.get("agents", {}).get(agent, {}))
    if os.environ.get("FORCE_PROVIDER"):  # servers can't run the claude CLI — force 'anthropic'
        merged["provider"] = os.environ["FORCE_PROVIDER"]
        model_env = os.environ.get(f"MODEL_{agent.upper()}") or os.environ.get("FORCE_MODEL")
        if model_env:
            merged["model"] = model_env
        elif merged.get("model") in ("sonnet", "opus", "haiku"):  # CLI aliases → API ids
            merged["model"] = {"sonnet": "claude-sonnet-5", "opus": "claude-opus-5",
                               "haiku": "claude-haiku-4-5-20251001"}[merged["model"]]
    merged.setdefault("provider", "mock")
    merged.setdefault("model", "mock-model")
    merged.setdefault("max_tokens", 4096)
    merged.setdefault("temperature", 0.2)
    return merged


def load_system_prompt(agent: str) -> str:
    path = AGENTS_DIR / f"{agent}.md"
    if not path.exists():
        raise FileNotFoundError(f"No prompt file for agent '{agent}' at {path}")
    return path.read_text()


def run_agent(
    agent: str,
    user_content: Any,
    tools: dict[str, Callable[..., Any]] | None = None,
    tool_schemas: list[dict[str, Any]] | None = None,
    provider_override: Any = None,
    extra_system: str = "",
) -> tuple[str, AgentTrace]:
    """Run one agent to completion. Returns (final_text, trace)."""
    cfg = load_agent_config(agent)
    system = load_system_prompt(agent)
    if extra_system:
        system = f"{system}\n\n---\n\n{extra_system}"
    provider = provider_override or get_provider(cfg["provider"])
    trace = AgentTrace(agent=agent, provider=provider.name, model=cfg["model"])

    # str → as-is; list → pre-built content blocks (e.g. text + image); else → JSON
    if isinstance(user_content, (str, list)):
        content = user_content
    else:
        content = json.dumps(user_content)
    messages: list[dict[str, Any]] = [{"role": "user", "content": content}]

    for _ in range(MAX_LOOPS):
        resp = provider.complete(
            system=system,
            messages=messages,
            tools=tool_schemas,
            model=cfg["model"],
            max_tokens=cfg["max_tokens"],
            temperature=cfg["temperature"],
        )
        if not resp.tool_calls:
            trace.steps.append({"type": "final", "text": (resp.text or "")[:2000]})
            return resp.text or "", trace

        # record assistant turn (text + tool calls), execute tools, feed results back
        messages.append({"role": "assistant", "content": _assistant_blocks(resp)})
        results = []
        for call in resp.tool_calls:
            fn = (tools or {}).get(call["name"])
            if fn is None:
                out: Any = {"error": f"unknown tool '{call['name']}'"}
            else:
                try:
                    out = fn(**call.get("arguments", {}))
                except Exception as e:  # tool bugs surface to the model, not as crashes
                    out = {"error": f"{type(e).__name__}: {e}"}
            trace.steps.append({"type": "tool", "name": call["name"],
                                "arguments": call.get("arguments", {}),
                                "result_preview": json.dumps(out, default=str)[:800]})
            results.append({
                "type": "tool_result",
                "tool_use_id": call.get("id", call["name"]),
                "content": json.dumps(out, default=str),
            })
        messages.append({"role": "user", "content": results})

    trace.steps.append({"type": "aborted", "reason": f"exceeded {MAX_LOOPS} tool loops"})
    return "", trace


def _assistant_blocks(resp) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if resp.text:
        blocks.append({"type": "text", "text": resp.text})
    for c in resp.tool_calls:
        blocks.append({"type": "tool_use", "id": c.get("id", c["name"]),
                       "name": c["name"], "input": c.get("arguments", {})})
    return blocks
