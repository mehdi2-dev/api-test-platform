"""LoginAttemptLimiter portunun bellek içi adaptörü (brute-force koruması).

Aynı e-posta + IP ile kısa sürede çok sayıda hatalı giriş denenirse bir süre kilitlenir
ve 429 (Too Many Requests) döner. Başarılı giriş sayacı sıfırlar.

Not: Sayaç uygulamanın belleğinde tutulur; backend tek süreç çalıştığı için yeterli.
Birden fazla sunucuya ölçeklenirse Redis'e taşınmalıdır.
"""

import time
from collections import deque
from threading import Lock

from app.core.config import settings


class LoginLimiter:
    def __init__(self, max_attempts: int, lock_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.lock_seconds = lock_seconds
        self._failures: dict[str, deque[float]] = {}
        self._lock = Lock()

    def _recent(self, key: str, now: float) -> deque[float]:
        attempts = self._failures.setdefault(key, deque())
        while attempts and now - attempts[0] > self.lock_seconds:
            attempts.popleft()
        return attempts

    def retry_after(self, key: str) -> int:
        """Kilitliyse kaç saniye beklenmeli; değilse 0."""
        now = time.monotonic()
        with self._lock:
            attempts = self._recent(key, now)
            if len(attempts) < self.max_attempts:
                return 0
            return max(1, int(self.lock_seconds - (now - attempts[0])))

    def failed(self, key: str) -> None:
        with self._lock:
            self._recent(key, time.monotonic()).append(time.monotonic())

    def succeeded(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()


login_limiter = LoginLimiter(settings.login_max_attempts, settings.login_lock_seconds)
