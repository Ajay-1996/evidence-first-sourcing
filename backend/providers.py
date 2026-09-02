"""Provider abstraction — the seam that keeps the agent layer frontier-model-agnostic.

An agent never imports a vendor SDK. It talks to `LLMProvider.complete()`, which takes the
markdown system prompt, a message list, and tool schemas, and returns either tool calls or a
final text. Which concrete provider (and model) backs each agent is decided in models.yaml.

Providers implemented:
  - MockProvider      : keyless development / plumbing tests. Follows a scripted playbook or
                        echoes deterministic output. NEVER used for the graded demo — the
                        assignment requires real loops.
  - AnthropicProvider : Claude via ANTHROPIC_API_KEY (lazy import so the dependency is
                        optional until the model decision is made).

Adding OpenAI/Gemini later = one more subclass, zero agent changes.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class ProviderResponse:
    text: Optional[str] = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # {id, name, arguments}
    stop_reason: str = "end"
    raw: Any = None


class LLMProvider:
    name = "base"

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> ProviderResponse:
        raise NotImplementedError


class MockProvider(LLMProvider):
    """Deterministic stand-in so the pipeline runs before the model decision is made.

    A test can hand it a `playbook`: a list of ProviderResponse-like dicts returned in order,
    letting us exercise the full tool loop (agent -> tool -> agent -> final) without a key.
    With no playbook it returns a labelled echo, which is enough for wiring checks.
    """

    name = "mock"

    def __init__(self, playbook: list[dict[str, Any]] | None = None):
        self._playbook = list(playbook or [])

    def complete(self, *, system, messages, tools, model, max_tokens, temperature) -> ProviderResponse:
        if self._playbook:
            step = self._playbook.pop(0)
            return ProviderResponse(
                text=step.get("text"),
                tool_calls=step.get("tool_calls", []),
                stop_reason=step.get("stop_reason", "tool_use" if step.get("tool_calls") else "end"),
            )
        last = next((m for m in reversed(messages) if m["role"] == "user"), {"content": ""})
        return ProviderResponse(
            text=json.dumps({
                "mock": True,
                "note": "MockProvider echo — set a real provider in models.yaml",
                "system_prompt_chars": len(system),
                "last_user_content_preview": str(last["content"])[:160],
            })
        )


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self) -> None:
        try:
            import anthropic  # lazy: only needed once the model decision lands
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "AnthropicProvider selected but the 'anthropic' package is not installed. "
                "Run: pip install anthropic"
            ) from e
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set — required for provider 'anthropic'.")
        headers = {}
        # identity-linked keys must name the workspace they act in
        if os.environ.get("ANTHROPIC_WORKSPACE_ID"):
            headers["anthropic-workspace-id"] = os.environ["ANTHROPIC_WORKSPACE_ID"]
        self._client = anthropic.Anthropic(default_headers=headers or None)

    def complete(self, *, system, messages, tools, model, max_tokens, temperature) -> ProviderResponse:
        kwargs: dict[str, Any] = dict(
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if tools:
            kwargs["tools"] = tools
        resp = self._client.messages.create(**kwargs)
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({"id": block.id, "name": block.name, "arguments": block.input})
        return ProviderResponse(
            text="\n".join(text_parts) or None,
            tool_calls=tool_calls,
            stop_reason=resp.stop_reason or "end",
            raw=resp,
        )


class ClaudeCodeProvider(LLMProvider):
    """Runs agents through the local `claude` CLI in headless mode (-p), so the user's
    Claude subscription powers the loops — no API key or credits required. Single-shot
    completions only: agents here never pass tool schemas (the propose-then-compute design
    keeps all tools as deterministic post-processing).

    The harness envs of a parent Claude Code session are stripped so the child uses the
    CLI's own login. Set ALLOW_READ_FILES=1 in the message content dict… (see complete()).
    """

    name = "claude_code"

    def complete(self, *, system, messages, tools, model, max_tokens, temperature) -> ProviderResponse:
        import subprocess
        # flatten: system + single user turn (text parts; image parts arrive as path notes)
        parts = [f"=== SYSTEM INSTRUCTIONS ===\n{system}\n=== INPUT ==="]
        allow_read = False
        for m in messages:
            c = m["content"]
            if isinstance(c, str):
                parts.append(c)
            else:
                for block in c:
                    if block.get("type") == "text":
                        parts.append(block["text"])
                        if "Read this image file" in block["text"]:
                            allow_read = True
        prompt = "\n\n".join(parts)
        env = {k: v for k, v in os.environ.items()
               if not (k.startswith("CLAUDE") or k.startswith("ANTHROPIC"))}
        env["PATH"] = os.environ.get("PATH", "")
        cmd = ["claude", "-p", prompt, "--output-format", "json",
               "--model", model, "--max-turns", "6",
               "--allowedTools", "Read" if allow_read else ""]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1200, env=env)
        if proc.returncode != 0 and not proc.stdout:
            raise RuntimeError(f"claude CLI failed: {proc.stderr[:400]}")
        payload = json.loads(proc.stdout)
        if payload.get("is_error"):
            raise RuntimeError(f"claude CLI error: {str(payload.get('result'))[:400]}")
        return ProviderResponse(text=payload.get("result") or "", raw=payload)


_REGISTRY: dict[str, Callable[[], LLMProvider]] = {
    "mock": MockProvider,
    "anthropic": AnthropicProvider,
    "claude_code": ClaudeCodeProvider,
}


def get_provider(name: str, **kwargs: Any) -> LLMProvider:
    try:
        factory = _REGISTRY[name]
    except KeyError:
        raise RuntimeError(f"Unknown provider '{name}'. Known: {sorted(_REGISTRY)}")
    return factory(**kwargs) if kwargs else factory()
