from app.orchestration.event_bus import EventBus
from app.orchestration.interaction_lock import InteractionLock
from app.orchestration.session_manager import SessionManager


class OnboardingFlow:
    def __init__(self, event_bus: EventBus, session_manager: SessionManager):
        self.event_bus = event_bus
        self.sessions = session_manager
        self._lock = InteractionLock()
        self._active = False
        self._pending_name = False

    @property
    def is_active(self) -> bool:
        return self._active

    async def begin(self):
        if self._active:
            return
        self._active = True
        self._pending_name = True
        await self._lock.acquire("onboarding")
        await self.event_bus.publish("registration_requested", {})
        print("[ONBOARD] Onboarding flow started — delegated to RegistrationManager")

    async def on_name_captured(self, data: dict):
        if not self._active:
            return
        self._pending_name = False
        self._active = False
        await self._lock.release("onboarding")
        print(f"[ONBOARD] Name captured: {data.get('name')} — onboarding complete")
        await self.event_bus.publish("user_registered", data)

    def abort(self):
        self._active = False
        self._pending_name = False

    def reset(self):
        self._active = False
        self._pending_name = False
