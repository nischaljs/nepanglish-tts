import asyncio

from app.conversation.contextual_greeter import ContextualGreeter
from app.conversation.onboarding_flow import OnboardingFlow
from app.orchestration.cooldown_manager import CooldownManager, PIPELINE_IDLE_TIMEOUT
from app.orchestration.event_bus import EventBus
from app.orchestration.interaction_lock import InteractionLock
from app.orchestration.session_manager import SessionManager, SessionState


INACTIVITY_CHECK_INTERVAL = 5.0


class ConversationOrchestrator:
    def __init__(self, face_monitor=None):
        self.event_bus = EventBus()
        self.lock = InteractionLock()
        self.sessions = SessionManager()
        self.cooldown = CooldownManager()
        self.greeter = ContextualGreeter(self.event_bus, self.sessions)
        self.onboarding = OnboardingFlow(self.event_bus, self.sessions)
        self._face_monitor = face_monitor
        self._face_resume_task: asyncio.Task | None = None
        self._running = False

    def set_face_monitor(self, face_monitor):
        self._face_monitor = face_monitor

    def _pause_face(self):
        if self._face_monitor and not self._face_monitor.is_paused:
            self._face_monitor.pause()

    def _resume_face(self):
        if self._face_monitor and self._face_monitor.is_paused:
            self._face_monitor.resume()

    async def start(self):
        self._running = True
        print("[ORCH] ConversationOrchestrator started")

        self.event_bus.subscribe("face_recognized", self._on_face_recognized)
        self.event_bus.subscribe("face_unknown", self._on_face_unknown)
        self.event_bus.subscribe("face_lost", self._on_face_lost)
        self.event_bus.subscribe("name_captured", self._on_name_captured)
        self.event_bus.subscribe("user_registered", self._on_user_registered)
        self.event_bus.subscribe("speech_started", self._on_speech_started)
        self.event_bus.subscribe("speech_ended", self._on_speech_ended)
        self.event_bus.subscribe("tts_started", self._on_tts_started)
        self.event_bus.subscribe("tts_finished", self._on_tts_finished)
        self.event_bus.subscribe("greeting", self._on_greeting_event)
        self.event_bus.subscribe("pipeline_complete", self._on_pipeline_complete)

        asyncio.create_task(self._inactivity_check_loop())

    async def stop(self):
        self._running = False
        self._cancel_face_resume()
        await self.lock.release_all()
        self._resume_face()

    async def _on_greeting_event(self, data: dict):
        self._pause_face()

    async def _on_pipeline_complete(self, data: dict):
        self.cooldown.set_post_pipeline_cooldown()
        self._schedule_face_resume()

    def _cancel_face_resume(self):
        if self._face_resume_task and not self._face_resume_task.done():
            self._face_resume_task.cancel()
            self._face_resume_task = None

    def _schedule_face_resume(self):
        self._cancel_face_resume()
        self._face_resume_task = asyncio.create_task(self._delayed_face_resume())

    async def _delayed_face_resume(self):
        try:
            await asyncio.sleep(PIPELINE_IDLE_TIMEOUT)
            if not self.lock.is_active:
                self._resume_face()
                self.cooldown.reset_pipeline_idle()
                print(f"[ORCH] Face RESUMED after {PIPELINE_IDLE_TIMEOUT}s pipeline idle")
            else:
                print(f"[ORCH] Pipeline idle elapsed but lock still active — face stays paused")
        except asyncio.CancelledError:
            pass

    async def _on_face_recognized(self, data: dict):
        if self.lock.is_active and not self.lock.is_inactive:
            print(f"[ORCH] Lock active — ignoring face_recognized")
            return

        if self.cooldown.post_pipeline_active:
            print(f"[ORCH] Post-pipeline cooldown active — ignoring face_recognized")
            return

        self._cancel_face_resume()
        self._pause_face()

        face_id = data["id"]
        session = self.sessions.get_or_create(face_id, data.get("name", ""))
        session.touch()

        await self.greeter.handle_recognized(data)

    async def _on_face_unknown(self, data: dict):
        if self.lock.is_active and not self.lock.is_inactive:
            print(f"[ORCH] Lock active — ignoring face_unknown")
            return

        if self.cooldown.post_pipeline_active:
            print(f"[ORCH] Post-pipeline cooldown active — ignoring face_unknown")
            return

        entry = self.cooldown.get("unknown")
        if not entry.can_onboard:
            print(f"[ORCH] Unknown onboarding cooldown active")
            return

        entry.mark_onboarding_done()

        self._cancel_face_resume()
        self._pause_face()

        session = self.sessions.active_session
        if session is None:
            session = self.sessions.get_or_create("unknown_pending")
            self.sessions._active_session_id = "unknown_pending"

        await self.onboarding.begin()

    async def _on_face_lost(self, data: dict):
        session = self.sessions.active_session
        if session:
            session.transition(SessionState.IDLE)
            await self.event_bus.publish("conversation_ended", {
                "face_id": data.get("id"),
                "reason": "face_lost",
            })

    async def _on_name_captured(self, data: dict):
        await self.onboarding.on_name_captured(data)

    async def _on_user_registered(self, data: dict):
        print(f"[ORCH] User registered: {data.get('name')}")

    async def _on_speech_started(self, data: dict):
        self._cancel_face_resume()
        self.cooldown.reset_pipeline_idle()
        await self.lock.acquire("speech")
        self.lock.touch()
        session = self.sessions.active_session
        if session:
            session.transition(SessionState.LISTENING)
            session.touch()

    async def _on_speech_ended(self, data: dict):
        session = self.sessions.active_session
        if session:
            session.transition(SessionState.PROCESSING)
            session.touch()

    async def _on_tts_started(self, data: dict):
        await self.lock.acquire("tts")
        self.lock.touch()
        session = self.sessions.active_session
        if session:
            session.transition(SessionState.SPEAKING)
            session.touch()

    async def _on_tts_finished(self, data: dict):
        await self.lock.release("tts")
        session = self.sessions.active_session
        if session:
            session.transition(SessionState.CONVERSING)
            session.touch()

    async def _inactivity_check_loop(self):
        while self._running:
            await asyncio.sleep(INACTIVITY_CHECK_INTERVAL)
            try:
                released = await self.lock.auto_release_if_inactive()
                if released:
                    print(f"[ORCH] System returned to idle after inactivity")
                    self._resume_face()
                    self.onboarding.abort()
                    session = self.sessions.active_session
                    if session:
                        await self.event_bus.publish("session_timeout", {
                            "face_id": session.face_id,
                        })
                        await self.event_bus.publish("conversation_ended", {
                            "face_id": session.face_id,
                            "reason": "inactivity_timeout",
                        })
                    self.sessions.clear_stale()
                    self.cooldown.cleanup_stale()
            except Exception as e:
                print(f"[ORCH] Inactivity check error: {e}")
