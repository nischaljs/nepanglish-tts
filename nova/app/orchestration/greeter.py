import asyncio
import time

from app.face.person_memory import get_memory
from app.orchestration.cooldown import CooldownManager
from app.orchestration.event_bus import EventBus
from app.orchestration.state import ConversationState, ConversationStateMachine


class Greeter:
    def __init__(
        self,
        event_bus: EventBus,
        state_machine: ConversationStateMachine,
        cooldown: CooldownManager,
    ):
        self.event_bus = event_bus
        self.state = state_machine
        self.cooldown = cooldown
        self._memory = get_memory()

    async def on_face_recognized(self, data: dict):
        if not self.state.can_greet():
            return
        face_id = data["id"]
        name = data["name"]
        if not self.cooldown.can_greet_face(face_id):
            return

        mem = self._memory.get(face_id, name)
        greeting = self._build_greeting(mem)
        await self.state.transition(ConversationState.GREETING)
        self.cooldown.mark_greeted(face_id)
        self._memory.touch(face_id)

        await self.event_bus.publish("greeting", {
            "type": "known",
            "name": name,
            "text": greeting,
            "face_id": face_id,
        })

    def _build_greeting(self, mem: dict) -> str:
        name = mem.get("name", "").title()
        visit_count = mem.get("visit_count", 1)
        notes = mem.get("notes", [])
        last_met = mem.get("last_met", "")

        if visit_count <= 1:
            return f"Welcome {name}. Great to meet you."

        time_since = self._time_since(last_met) if last_met else ""

        if notes:
            topic = notes[-1].replace("interest: ", "").replace("fact: ", "")
            if "AI" in topic or "robot" in topic:
                return f"Welcome back {name}. Still exploring the world of AI?"
            return f"Welcome back {name}. Last time we talked about {topic}."
        if time_since:
            return f"Welcome back {name}. It's been {time_since} since we last spoke."
        return f"Welcome back {name}."

    def _time_since(self, timestamp: str) -> str:
        try:
            last = time.mktime(time.strptime(timestamp.split(".")[0], "%Y-%m-%dT%H:%M:%S"))
            diff = time.time() - last
            if diff < 3600:
                return "a while"
            elif diff < 86400:
                return "today"
            elif diff < 604800:
                days = int(diff / 86400)
                return f"{days} day{'s' if days > 1 else ''} ago"
            else:
                weeks = int(diff / 604800)
                return f"{weeks} week{'s' if weeks > 1 else ''} ago"
        except (ValueError, OSError):
            return ""
