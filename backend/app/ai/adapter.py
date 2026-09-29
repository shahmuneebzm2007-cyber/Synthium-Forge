"""
AI Privacy Firewall + Multi-Provider Key Rotation + LLM Adapter.

The Firewall is the LAW: NO raw row data EVER reaches an LLM.
Keys rotate automatically. Fallback works offline.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
import threading
from typing import Any, Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel

from app.core.config import get_config


# ═══════════════════════════════════════════════════════════════════
#  PRIVACY FIREWALL
# ═══════════════════════════════════════════════════════════════════

class PrivacyFirewall:
    """Ensures no raw row data ever reaches an LLM.

    ALLOW-LIST only:
      ✓ Column names, inferred types, null rates
      ✓ Aggregates: min/max/mean, quantiles, distinct counts
      ✓ Category names ONLY IF not PII and cardinality ≤ 50
      ✓ User's own prompt text

    NEVER ALLOW:
      ✗ Raw row values
      ✗ Free-text cell contents
      ✗ Any value from PII-flagged columns
      ✗ Uploaded file bytes
    """

    def __init__(self):
        self.payloads: list[dict] = []

    def build_payload(self, profile: dict, prompt: str = "",
                      pii_columns: set[str] | None = None) -> dict:
        """Build a safe payload from a data profile."""
        pii_columns = pii_columns or set()
        safe_columns = []

        for col in profile.get("columns", []):
            name = col["name"]
            is_pii = col.get("pii", "none") != "none" or name in pii_columns

            safe_col: dict[str, Any] = {
                "name": name,
                "kind": col.get("kind", "text"),
                "null_rate": col.get("null_rate", 0),
                "n_unique": col.get("n_unique", 0),
                "is_pii": is_pii,
            }

            # Aggregates (never raw values)
            if not is_pii:
                for key in ("min", "max", "mean", "median", "std", "quantiles",
                            "skewness", "kurtosis", "date_range_days"):
                    if key in col:
                        safe_col[key] = col[key]

                # Category names only if not PII and low cardinality
                if col.get("kind") == "cat" and col.get("n_unique", 999) <= 50:
                    if "top_values" in col:
                        safe_col["categories"] = list(col["top_values"].keys())
                    elif "weights" in col:
                        safe_col["categories"] = list(col["weights"].keys())

            safe_columns.append(safe_col)

        payload = {
            "n_rows": profile.get("rows", 0),
            "n_columns": len(safe_columns),
            "columns": safe_columns,
            "prompt": prompt,
        }

        self.payloads.append(payload)
        return payload

    def validate_payload(self, payload: dict,
                         source_df: pd.DataFrame | None = None) -> tuple[bool, list[str]]:
        """Scan payload for leaked source values. Returns (is_safe, violations)."""
        violations = []
        if source_df is None:
            return True, []

        payload_str = json.dumps(payload, default=str)
        for col in source_df.columns:
            vals = source_df[col].dropna().astype(str).unique()
            for v in vals[:100]:  # Sample check
                if len(v) > 5 and v in payload_str:
                    # Check if it's not just a column name or stat
                    if v not in [col, str(source_df[col].dtype)]:
                        violations.append(f"Possible value leak: '{v}' from column '{col}'")

        return len(violations) == 0, violations

    def get_payload_hash(self, payload: dict) -> str:
        """Deterministic hash for manifest tracking."""
        content = json.dumps(payload, sort_keys=True, default=str)
        return f"sha256:{hashlib.sha256(content.encode()).hexdigest()}"

    def get_summary(self) -> dict:
        """Summary for the 'What the AI saw' panel."""
        return {
            "total_calls": len(self.payloads),
            "payloads": [
                {"hash": self.get_payload_hash(p),
                 "columns_shared": len(p.get("columns", [])),
                 "prompt_length": len(p.get("prompt", "")),
                 "pii_columns_redacted": sum(1 for c in p.get("columns", []) if c.get("is_pii"))}
                for p in self.payloads
            ],
        }


# ═══════════════════════════════════════════════════════════════════
#  KEY ROTATOR
# ═══════════════════════════════════════════════════════════════════

class KeyHealth:
    def __init__(self, key: str, key_id: str, provider: str):
        self.key = key
        self.key_id = key_id
        self.provider = provider
        self.successes = 0
        self.failures = 0
        self.total_latency_ms = 0
        self.total_tokens = 0
        self.rate_limited_until: float = 0
        self.last_error: str = ""

    @property
    def is_available(self) -> bool:
        return time.time() > self.rate_limited_until

    @property
    def health_score(self) -> float:
        total = self.successes + self.failures
        if total == 0:
            return 1.0
        rate = self.successes / total
        avg_latency = (self.total_latency_ms / max(self.successes, 1)) / 1000
        return rate / max(avg_latency, 0.1)


class KeyRotator:
    """Round-robin API key rotation with health tracking."""

    def __init__(self):
        self._keys: dict[str, list[KeyHealth]] = {}
        self._index: dict[str, int] = {}
        self._lock = threading.Lock()

    def add_keys(self, provider: str, keys: list[str]):
        self._keys[provider] = []
        for i, k in enumerate(keys):
            kid = f"{provider}_{i}"
            self._keys[provider].append(KeyHealth(k, kid, provider))
        self._index[provider] = 0

    def get_next_key(self, provider: str) -> tuple[str, str]:
        """Get the next available key via round-robin. Returns (key, key_id)."""
        with self._lock:
            pool = self._keys.get(provider, [])
            if not pool:
                raise ValueError(f"No API keys configured for {provider}")

            n = len(pool)
            start = self._index.get(provider, 0)
            for offset in range(n):
                idx = (start + offset) % n
                kh = pool[idx]
                if kh.is_available:
                    self._index[provider] = (idx + 1) % n
                    return kh.key, kh.key_id

            # All rate-limited — return the one with shortest cooldown
            best = min(pool, key=lambda k: k.rate_limited_until)
            return best.key, best.key_id

    def report_success(self, key_id: str, latency_ms: int, tokens: int = 0):
        kh = self._find(key_id)
        if kh:
            kh.successes += 1
            kh.total_latency_ms += latency_ms
            kh.total_tokens += tokens

    def report_failure(self, key_id: str, error: str):
        kh = self._find(key_id)
        if kh:
            kh.failures += 1
            kh.last_error = error

    def report_rate_limit(self, key_id: str, retry_after: int = 60):
        kh = self._find(key_id)
        if kh:
            kh.rate_limited_until = time.time() + retry_after
            kh.failures += 1

    def get_status(self) -> dict:
        return {
            provider: [
                {"key_id": kh.key_id, "successes": kh.successes,
                 "failures": kh.failures, "available": kh.is_available,
                 "health_score": round(kh.health_score, 3)}
                for kh in pool
            ]
            for provider, pool in self._keys.items()
        }

    def _find(self, key_id: str) -> Optional[KeyHealth]:
        for pool in self._keys.values():
            for kh in pool:
                if kh.key_id == key_id:
                    return kh
        return None


# ═══════════════════════════════════════════════════════════════════
#  LLM ADAPTER
# ═══════════════════════════════════════════════════════════════════

class LLMAdapter:
    """Unified LLM adapter with multi-provider support, rotation, and fallback."""

    def __init__(self, firewall: PrivacyFirewall | None = None,
                 rotator: KeyRotator | None = None):
        self.config = get_config()
        self.firewall = firewall or PrivacyFirewall()
        self.rotator = rotator or KeyRotator()
        self.usage = {"calls": 0, "tokens": 0, "fallback_used": False}

        # Initialize rotator with configured keys
        if self.config.ai.anthropic_keys:
            self.rotator.add_keys("anthropic", self.config.ai.anthropic_keys)
        if self.config.ai.openai_keys:
            self.rotator.add_keys("openai", self.config.ai.openai_keys)
        if self.config.ai.gemini_keys:
            self.rotator.add_keys("gemini", self.config.ai.gemini_keys)

    async def call(self, prompt: str, system: str = "",
                   provider: str | None = None,
                   max_tokens: int = 4096,
                   temperature: float = 0.3) -> dict:
        """Call an LLM with automatic retry, rotation, and fallback.

        Returns parsed JSON dict from the LLM response.
        """
        if self.config.ai.offline:
            self.usage["fallback_used"] = True
            return {"error": "offline_mode", "fallback": True}

        provider = provider or self.config.ai.provider
        retries = self.config.ai.max_retries

        for attempt in range(retries + 1):
            try:
                key, key_id = self.rotator.get_next_key(provider)
                start = time.time()

                if provider == "anthropic":
                    raw = await self._call_anthropic(prompt, system, key, max_tokens, temperature)
                elif provider == "openai":
                    raw = await self._call_openai(prompt, system, key, max_tokens, temperature)
                elif provider == "gemini":
                    raw = await self._call_gemini(prompt, system, key, max_tokens, temperature)
                else:
                    raise ValueError(f"Unknown provider: {provider}")

                latency = int((time.time() - start) * 1000)
                self.rotator.report_success(key_id, latency)
                self.usage["calls"] += 1

                # Parse JSON
                parsed = self._extract_json(raw)
                return parsed

            except Exception as e:
                error_str = str(e)
                if "rate" in error_str.lower() or "429" in error_str:
                    self.rotator.report_rate_limit(key_id, 60)
                else:
                    self.rotator.report_failure(key_id, error_str)

                if attempt < retries:
                    await asyncio.sleep(1)
                    continue

                self.usage["fallback_used"] = True
                return {"error": error_str, "fallback": True}

    async def _call_anthropic(self, prompt, system, key, max_tokens, temp) -> str:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=key)
        msg = await client.messages.create(
            model=self.config.ai.model,
            max_tokens=max_tokens,
            temperature=temp,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text

    async def _call_openai(self, prompt, system, key, max_tokens, temp) -> str:
        import openai
        # Connect via OpenRouter
        client = openai.AsyncOpenAI(
            api_key=key, 
            base_url="https://openrouter.ai/api/v1"
        )
        resp = await client.chat.completions.create(
            model="openai/gpt-4o-mini",
            max_tokens=max_tokens,
            temperature=temp,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content or ""

    async def _call_gemini(self, prompt, system, key, max_tokens, temp) -> str:
        import urllib.request
        import json
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
        data = json.dumps({
            "contents": [{"parts": [{"text": f"{system}\n\n{prompt}"}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temp
            }
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        resp = await asyncio.to_thread(urllib.request.urlopen, req)
        result = json.loads(resp.read().decode())
        try:
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            return ""

    def _extract_json(self, raw: str) -> dict:
        """Extract JSON from LLM response, handling markdown code blocks."""
        # Try direct parse
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Try extracting from code block
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding JSON object
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

        return {"raw_response": raw, "parse_error": True}

    def get_usage(self) -> dict:
        return dict(self.usage)
