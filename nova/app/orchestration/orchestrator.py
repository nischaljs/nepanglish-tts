import asyncio

from app.face.camera import Camera
from app.face.preview import CameraPreview
from app.face.person_memory import get_memory
from app.orchestration.conversation_orchestrator import ConversationOrchestrator
from app.orchestration.cooldown import CooldownManager as LegacyCooldownManager
from app.orchestration.event_bus import EventBus
from app.orchestration.state import ConversationState, ConversationStateMachine
from app.orchestration.face_monitor import FaceMonitor
from app.orchestration.greeter import Greeter
from app.orchestration.registration import RegistrationManager


class Orchestrator:
    def __init__(self):
        self.event_bus = EventBus()
        self.state = ConversationStateMachine(self.event_bus)
        self.cooldown = LegacyCooldownManager()
        self.camera = None
        self.preview = None
        self.face_monitor = None
        self.greeter = None
        self.registration = None
        self._memory = get_memory()
        self._background_tasks = []
        self._running = False

        self.conversation = ConversationOrchestrator()

    async def start(self):
        self._running = True
        print("[ORCH] Starting orchestrator...")

        await self.conversation.start()

        self.greeter = Greeter(self.event_bus, self.state, self.cooldown)
        self.registration = RegistrationManager(self.event_bus, self.state, self.cooldown)

        self.event_bus.subscribe("registration_requested", self.registration.on_registration_requested)
        self.event_bus.subscribe("name_captured", self.registration.on_name_captured)

        self.event_bus.subscribe("speak", self._on_speak)
        self.event_bus.subscribe("greeting", self._on_greeting)
        self.event_bus.subscribe("registration_complete", self._on_registration_complete)

        self.event_bus.subscribe("face_detected", self._on_face_context_update)
        self.event_bus.subscribe("face_recognized", self._on_face_context_update)
        self.event_bus.subscribe("face_unknown", self._on_face_context_update_unknown)
        self.event_bus.subscribe("face_lost", self._on_face_context_clear)
        print("[ORCH] Event bus subscriptions set up")

        print("[ORCH] Initializing camera...")
        self.camera = Camera()
        self.preview = CameraPreview()
        self.preview.start()
        print("[ORCH] Camera + preview started")

        self.face_monitor = FaceMonitor(self.event_bus, self.state, self.cooldown, preview=self.preview)
        self.conversation.set_face_monitor(self.face_monitor)
        print("[ORCH] FaceMonitor created")

        self._background_tasks.append(asyncio.create_task(self.face_monitor.run()))
        self._background_tasks.append(asyncio.create_task(self._memory_flush_loop()))
        self._background_tasks.append(asyncio.create_task(self._state_cleanup_loop()))
        print(f"[ORCH] Started {len(self._background_tasks)} background tasks")

    async def stop(self):
        print("[ORCH] Stopping orchestrator...")
        self._running = False
        await self.conversation.stop()
        for task in self._background_tasks:
            task.cancel()
        if self.camera:
            self.camera.release()
            print("[ORCH] Camera released")
        if self.preview:
            self.preview.stop()
        await self._memory.flush_all()
        print("[ORCH] Orchestrator stopped")

    async def _memory_flush_loop(self):
        while self._running:
            await asyncio.sleep(30)
            await self._memory.flush()

    async def _state_cleanup_loop(self):
        while self._running:
            await asyncio.sleep(5)
            if not self.cooldown.face_is_present:
                if self.state.state in (ConversationState.FACE_DETECTED, ConversationState.GREETING):
                    print(f"[ORCH] Cleanup: state={self.state.state} → IDLE")
                    await self.state.transition(ConversationState.IDLE)
                    self.cooldown.reset_session()

    async def _on_speak(self, data: dict):
        text = data.get("text", "")
        emotion = data.get("emotion", "friendly")
        if not text:
            return
        print(f"[ORCH] Speak event: '{text[:80]}' emotion={emotion}")
        from app.tts.tts_engine import text_to_speech, play_audio
        from app.communication.websocket import send_websocket_message
        await self.state.transition(ConversationState.SPEAKING)
        await self.event_bus.publish("tts_started", {"text": text})
        file = await text_to_speech(text, emotion)
        print(f"[ORCH] TTS rendered, playing...")
        await play_audio(file)
        await self.event_bus.publish("tts_finished", {"text": text})
        try:
            await send_websocket_message("start_stream")
        except Exception as e:
            print(f"[ORCH] Error sending start_stream: {e}")
        await self.state.transition(ConversationState.IDLE)

    async def _on_greeting(self, data: dict):
        text = data.get("text", "")
        if not text:
            return
        print(f"[ORCH] Greeting event: '{text[:80]}'")
        from app.tts.tts_engine import text_to_speech, play_audio
        from app.communication.websocket import send_websocket_message
        await self.event_bus.publish("tts_started", {"text": text})
        file = await text_to_speech(text, "friendly")
        await play_audio(file)
        await self.event_bus.publish("tts_finished", {"text": text})
        try:
            await send_websocket_message("start_stream")
        except Exception as e:
            print(f"[ORCH] Error sending start_stream: {e}")
        await self.state.transition(ConversationState.CONVERSING)

    async def _on_registration_complete(self, data: dict):
        name = data.get("name", "")
        face_id = data.get("id", "")
        print(f"[ORCH] Registration complete: {name} (id={face_id})")
        self.cooldown.mark_greeted(face_id)

    async def _on_face_context_update(self, data: dict):
        from app.pipeline.process_audio import update_face_context
        if data and data.get("unknown"):
            update_face_context(None)
            return
        print(f"[ORCH] Face context update: {data}")
        update_face_context(data)

    async def _on_face_context_update_unknown(self, data: dict):
        from app.pipeline.process_audio import update_face_context
        print(f"[ORCH] Face context clear (unknown)")
        update_face_context(None)

    async def _on_face_context_clear(self, data: dict):
        from app.pipeline.process_audio import update_face_context
        print(f"[ORCH] Face context clear (face lost)")
        update_face_context(None)

    @property
    def current_face_context(self) -> dict | None:
        return getattr(self.face_monitor, "_current_face", None) if self.face_monitor else None