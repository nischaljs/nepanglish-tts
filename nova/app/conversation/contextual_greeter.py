import time

from app.face.person_memory import get_memory
from app.orchestration.cooldown_manager import CooldownManager
from app.orchestration.event_bus import EventBus
from app.orchestration.interaction_lock import InteractionLock
from app.orchestration.session_manager import SessionManager


class ContextualGreeter:
    def __init__(self, event_bus: EventBus, session_manager: SessionManager):
        self.event_bus = event_bus
        self.sessions = session_manager
        self._lock = InteractionLock()
        self._cooldown = CooldownManager()
        self._memory = get_memory()

    async def handle_recognized(self, data: dict):
        if self._lock.is_active and not self._lock.is_inactive:
            print(f"[GREETER] Interaction active — suppressing greeting")
            return

        face_id = data["id"]
        name = data["name"]

        entry = self._cooldown.get(face_id)
        if not entry.can_greet:
            print(f"[GREETER] Greeting cooldown active for {name}")
            return

        mem = self._memory.get(face_id, name)
        greeting = self._build_greeting(mem)

        entry.mark_greeted()
        self._memory.touch(face_id)

        await self._lock.acquire("greeting")
        session = self.sessions.activate(face_id)
        session.name = name
        from app.orchestration.session_manager import SessionState
        session.transition(SessionState.GREETING)

        await self.event_bus.publish("greeting", {
            "type": "known",
            "name": name,
            "text": greeting,
            "face_id": face_id,
        })

        await self._lock.release("greeting")
        print(f"[GREETER] Greeted {name}: '{greeting}'")

    def _build_greeting(self, mem: dict) -> str:
        name = mem.get("name", "").title()
        visit_count = mem.get("visit_count", 1)
        notes = mem.get("notes", [])
        last_met = mem.get("last_met", "")

        if visit_count <= 1:
            return f"Welcome {name}. Great to meet you."

        time_since = self._time_since(last_met) if last_met else ""

        if notes:
            topic = notes[-1].replace("interest: ", "").replace("fact: ", "").replace("tone: ", "")
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
