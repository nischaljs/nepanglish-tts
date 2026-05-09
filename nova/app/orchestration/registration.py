import asyncio
import json
import re
import time

import cv2
import numpy as np

from app.face.face_tools import FrameBuffer, get_bridge, get_collector
from app.face.person_memory import get_memory
from app.orchestration.cooldown import CooldownManager
from app.orchestration.event_bus import EventBus
from app.orchestration.state import ConversationState, ConversationStateMachine
from face_recognition_system.detector import detect_faces

UNKNOWN_SETTLE_SECONDS = 5


class RegistrationManager:
    def __init__(
        self,
        event_bus: EventBus,
        state_machine: ConversationStateMachine,
        cooldown: CooldownManager,
    ):
        self.event_bus = event_bus
        self.state = state_machine
        self.cooldown = cooldown
        self._bridge = get_bridge()
        self._memory = get_memory()
        self._collector = get_collector()
        self._unknown_first_seen = 0.0
        self._registering = False
        self._collect_task = None

    async def on_face_unknown(self, data: dict):
        if self._registering:
            return
        if not self.cooldown.can_ask_name():
            return
        if not self.state.can_greet():
            return

        now = time.time()
        if self._unknown_first_seen == 0:
            self._unknown_first_seen = now
            return

        if now - self._unknown_first_seen < UNKNOWN_SETTLE_SECONDS:
            return

        self.cooldown.mark_name_asked()
        await self.event_bus.publish("registration_requested", {})

    async def on_registration_requested(self, data: dict):
        if self._registering:
            return
        self._registering = True
        await self.state.transition(ConversationState.REGISTERING)

        await self.event_bus.publish("speak", {
            "text": "Hi, I don't think we've met before. How are you?",
            "emotion": "friendly",
        })

        await asyncio.sleep(2)

        await self.event_bus.publish("speak", {
            "text": "Can I have your name?",
            "emotion": "friendly",
        })

        await self._start_stream_for_name()
        self._collect_task = asyncio.create_task(self._collect_registration_frames())

    async def _start_stream_for_name(self):
        from app.communication.websocket import send_websocket_message
        await send_websocket_message(json.dumps({
            "type": "stream_start",
            "reason": "name_capture",
        }))

    async def on_name_captured(self, data: dict):
        transcript = data.get("transcript", "")
        name = self._extract_name(transcript)
        if not name:
            await self.event_bus.publish("speak", {
                "text": "I'm sorry, I didn't catch that. Could you repeat your name?",
                "emotion": "friendly",
            })
            self._registering = False
            return

        if self._collect_task:
            self._collect_task.cancel()
            self._collect_task = None

        frame = self._get_best_registration_frame()
        if frame is not None:
            result = self._bridge.register(frame, name)
            if result:
                face_id = result["id"]
                self._collector.clear()
                self._registering = False
                await self.event_bus.publish("registration_complete", {
                    "id": face_id,
                    "name": name,
                })
                await self.event_bus.publish("speak", {
                    "text": f"Nice to meet you {name.title()}. I'll remember you next time.",
                    "emotion": "cheerful",
                })
                self.cooldown.reset_unknown()
                return

        await self.event_bus.publish("speak", {
            "text": "I couldn't see your face clearly. Could you look at the camera?",
            "emotion": "friendly",
        })
        self._registering = False

    def _get_best_registration_frame(self):
        if self._collector.count > 0:
            best = max(self._collector.samples, key=lambda s: s[1])
            return best[0]
        fb = FrameBuffer()
        frame, _ = fb.get()
        if frame is not None:
            return cv2.resize(frame, None, fx=0.5, fy=0.5)
        return None

    async def _collect_registration_frames(self):
        fb = FrameBuffer()
        DETECT_SCALE = 0.5
        while self._registering and not self._collector.full:
            frame = fb.get_frame()
            if frame is not None:
                small = cv2.resize(frame, None, fx=DETECT_SCALE, fy=DETECT_SCALE)
                faces = detect_faces(small)
                if faces:
                    score = float(faces[0].get("score", 0.5))
                    self._collector.add(small, score)
            await asyncio.sleep(0.5)

    def _extract_name(self, transcript: str) -> str:
        transcript = transcript.strip()
        patterns = [
            r"(?:my name is|i am|i'm|call me|it's|this is)\s+(\w+)",
            r"^(\w+)\s+(?:is my name|here)$",
        ]
        for pat in patterns:
            m = re.search(pat, transcript, re.IGNORECASE)
            if m:
                return m.group(1).strip().capitalize()
        words = transcript.split()
        if len(words) == 1 and len(words[0]) > 1:
            return words[0].capitalize()
        if len(words) == 2 and len(words[0]) > 1:
            return words[0].capitalize()
        return ""

    def reset(self):
        self._unknown_first_seen = 0.0
        self._registering = False
        if self._collect_task:
            self._collect_task.cancel()
            self._collect_task = None
