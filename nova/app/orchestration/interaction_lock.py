import asyncio
import time


INACTIVITY_TIMEOUT = 30.0


class InteractionLock:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._locked = False
            cls._instance._lockers = set()
            cls._instance._last_activity = 0.0
            cls._instance._lock = asyncio.Lock()
        return cls._instance

    @property
    def is_active(self) -> bool:
        return self._locked

    @property
    def last_activity(self) -> float:
        return self._last_activity

    def touch(self):
        self._last_activity = time.time()

    async def acquire(self, reason: str = "unknown"):
        async with self._lock:
            was_locked = self._locked
            self._locked = True
            self._lockers.add(reason)
            self._last_activity = time.time()
            if not was_locked:
                print(f"[LOCK] Acquired (reason={reason})")

    async def release(self, reason: str = "unknown"):
        async with self._lock:
            self._lockers.discard(reason)
            if not self._lockers:
                self._locked = False
                self._last_activity = 0.0
                print(f"[LOCK] Released — all lockers done")

    async def release_all(self):
        async with self._lock:
            self._locked = False
            self._lockers.clear()
            self._last_activity = 0.0
            print(f"[LOCK] Force-released all locks")

    @property
    def is_inactive(self) -> bool:
        if not self._locked:
            return True
        elapsed = time.time() - self._last_activity
        return elapsed > INACTIVITY_TIMEOUT

    async def auto_release_if_inactive(self) -> bool:
        if self._locked and self.is_inactive:
            print(f"[LOCK] Auto-releasing after {INACTIVITY_TIMEOUT}s inactivity")
            await self.release_all()
            return True
        return False

    def get_lockers(self) -> set:
        return set(self._lockers)
