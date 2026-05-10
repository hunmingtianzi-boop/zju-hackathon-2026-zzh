"""DeepSeek API client — shared by all KIA pipeline stages.

Usage:
    from llm_client import chat, chat_json
    answer = chat("你是谁？")
    data = chat_json([...messages...])
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

def _load_env():
    """Load .env from project root if not already in os.environ."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value

_load_env()

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

import urllib.request
import urllib.error

def _api_call(messages: list[dict[str, str]], temperature: float = 0.3, max_tokens: int = 2048) -> str:
    """Raw DeepSeek chat completion call. Returns response text or empty string on failure."""
    if not API_KEY:
        return ""

    body = json.dumps({
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }).encode("utf-8")

    url = f"{BASE_URL.rstrip('/')}/v1/chat/completions"
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {API_KEY}")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[LLM] API call failed: {e}")
        return ""


def chat(prompt: str, system: str = "你是专业医学知识助手。", temperature: float = 0.3) -> str:
    """Single-turn chat."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    return _api_call(messages, temperature=temperature)


def chat_json(prompt: str, system: str = "你是专业医学知识助手。请严格输出JSON。", temperature: float = 0.1) -> Any:
    """Single-turn chat, parse response as JSON."""
    text = chat(prompt, system=system, temperature=temperature)
    if not text:
        return None

    # Try to extract JSON from markdown code blocks
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if json_match:
        text = json_match.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON array or object
        for pattern in [r"\[[\s\S]*\]", r"\{[\s\S]*\}"]:
            m = re.search(pattern, text)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    continue
        print(f"[LLM] Failed to parse JSON from: {text[:300]}")
        return None


def chat_batch(prompts: list[str], system: str = "你是专业医学知识助手。", temperature: float = 0.3) -> list[str]:
    """Sequential batch chat (DeepSeek API doesn't support native batching)."""
    results = []
    for i, prompt in enumerate(prompts):
        result = chat(prompt, system=system, temperature=temperature)
        results.append(result)
        if i < len(prompts) - 1:
            time.sleep(0.3)  # Rate limit protection
    return results
