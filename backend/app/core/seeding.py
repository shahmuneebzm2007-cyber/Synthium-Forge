"""
Reproducible, order-independent random number generation.

Every component (table, column, engine) gets its own independent RNG stream
derived from one master seed. This means:
  - Same seed + same config = byte-identical output
  - Adding a new table doesn't change existing tables' output
  - Parallel generation is safe (no shared state)
"""
import hashlib
from typing import Union

import numpy as np


def _path_hash(*path: str) -> int:
    """Deterministic hash of a path to a 64-bit integer."""
    data = "/".join(str(p) for p in path).encode("utf-8")
    return int.from_bytes(hashlib.sha256(data).digest()[:8], "big")


def rng_for(seed: int, *path: str) -> np.random.Generator:
    """Create an independent, repeatable random stream for a named component.
    
    Usage:
        rng_for(42, 'customers')           # always the same, regardless of what else ran
        rng_for(42, 'orders', 'status')    # sub-stream for a specific column
        rng_for(42, 'items', 'sku', '3')   # even deeper nesting
    
    The path ensures independence: rng_for(42, 'A') and rng_for(42, 'B')
    produce completely different sequences, and neither affects the other.
    """
    h = _path_hash(*path)
    seq = np.random.SeedSequence([int(seed), h])
    return np.random.default_rng(seq)


def spawn_rngs(seed: int, base_path: str, n: int) -> list[np.random.Generator]:
    """Spawn N independent RNGs from one parent path.
    
    Useful for generating N tables or N chunks in parallel.
    """
    parent = np.random.SeedSequence([int(seed), _path_hash(base_path)])
    children = parent.spawn(n)
    return [np.random.default_rng(child) for child in children]


def deterministic_hash(data: Union[str, bytes], length: int = 12) -> str:
    """Short deterministic hash for pseudonymization, manifest IDs, etc."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:length]


def file_sha256(path: str) -> str:
    """Compute SHA-256 of a file for manifest verification."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def content_sha256(data: bytes) -> str:
    """SHA-256 of in-memory bytes."""
    return f"sha256:{hashlib.sha256(data).hexdigest()}"
