"""Per-IP token bucket for the solve endpoints, so a judge or a bot can't pin the CPU."""

from __future__ import annotations

import ipaddress
import threading
import time
from dataclasses import dataclass

from fastapi import Request


@dataclass
class _Bucket:
    tokens: float
    stamp: float


class RateLimiter:
    def __init__(self, per_minute: float, burst: int, trusted_proxies: list[str]) -> None:
        self.rate = per_minute / 60.0
        self.burst = float(burst)
        self.trusted = [ipaddress.ip_network(cidr, strict=False) for cidr in trusted_proxies if cidr]
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def client_ip(self, request: Request) -> str:
        peer = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded and self._is_trusted(peer):
            # The trusted proxy appends the address it saw last; anything left of it is client-supplied.
            return forwarded.split(",")[-1].strip()
        return peer

    def _is_trusted(self, host: str) -> bool:
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return False
        return any(ip in net for net in self.trusted)

    def allow(self, key: str) -> tuple[bool, float]:
        """Take one token for `key`. Returns (allowed, seconds until the next token)."""
        now = time.monotonic()
        with self._lock:
            if len(self._buckets) > 10_000:
                full = self.burst / self.rate
                self._buckets = {k: v for k, v in self._buckets.items() if now - v.stamp < full}
            bucket = self._buckets.get(key) or _Bucket(self.burst, now)
            bucket.tokens = min(self.burst, bucket.tokens + (now - bucket.stamp) * self.rate)
            bucket.stamp = now
            self._buckets[key] = bucket
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True, 0.0
            return False, (1.0 - bucket.tokens) / self.rate
