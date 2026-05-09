import asyncio
import time
from enum import Enum

from app.orchestration.event_bus import EventBus


SESSION_IDLE_TIMEOUT = 30.0
SESSION_FACE_LOST_TIMEOUT = 10.0


class SessionState(Enum):
    IDLE = "idle"
    FACE_PRESENT = "face_present"
    GREETING = "greeting"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    CONVERSING = "conversing"
    WAITING = "waiting"
    SESSION_TIMEOUT = "session_timeout"


VALID_TRANSITIONS = {
    SessionState.IDLE: [SessionState.FACE_PRESENT, SessionState.LISTENING],
    SessionState.FACE_PRESENT: [SessionState.GREETING, SessionState.CONVERSING, SessionState.IDLE, SessionState.SESSION_TIMEOUT],
    SessionState.GREETING: [SessionState.CONVERSING, SessionState.LISTENING, SessionState.IDLE, SessionState.SESSION_TIMEOUT],
    SessionState.CONVERSING: [SessionState.LISTENING, SessionState.SPEAKING, SessionState.PROCESSING, SessionState.WAITING, SessionState.IDLE, SessionState.SESSION_TIMEOUT],
    SessionState.LISTENING: [SessionState.PROCESSING, SessionState.IDLE, SessionState.SESSION_TIMEOUT],
    SessionState.PROCESSING: [SessionState.SPEAKING, SessionState.CONVERSING, SessionState.IDLE, SessionState.SESSION_TIMEOUT],
    SessionState.SPEAKING: [SessionState.LISTENING, SessionState.CONVERSING, SessionState.IDLE, SessionState.SESSION_TIMEOUT],
    SessionState.WAITING: [SessionState.LISTENING, SessionState.GREETING, SessionState.IDLE, SessionState.SESSION_TIMEOUT],
    SessionState.SESSION_TIMEOUT: [SessionState.IDLE, SessionState.FACE_PRESENT],
}


class ConversationSession:
    def __init__(self, face_id: str, name: str = ""):
        self.face_id = face_id
        self.name = name
        self.state = SessionState.IDLE
        self.created_at = time.time()
        self.last_activity = time.time()
        self.onboarding_state = None
        self.is_onboarding = False
        self.pipeline_busy = False

    def touch(self):
        self.last_activity = time.time()

    @property
    def is_idle(self) -> bool:
        return self.state == SessionState.IDLE

    @property
    def is_stale(self) -> bool:
        return (time.time() - self.last_activity) > SESSION_IDLE_TIMEOUT

    @property
    def face_considered_lost(self) -> bool:
        return (time.time() - self.last_activity) > SESSION_FACE_LOST_TIMEOUT

    def can_transition(self, new_state: SessionState) -> bool:
        return new_state in VALID_TRANSITIONS.get(self.state, [])

    def transition(self, new_state: SessionState) -> bool:
        if not self.can_transition(new_state):
            return False
        old = self.state
        self.state = new_state
        self.touch()
        return True


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, ConversationSession] = {}
        self._active_session_id: str | None = None
        self._event_bus = EventBus()

    @property
    def active_session(self) -> ConversationSession | None:
        if self._active_session_id and self._active_session_id in self._sessions:
            return self._sessions[self._active_session_id]
        return None

    @property
    def active_face_id(self) -> str | None:
        s = self.active_session
        return s.face_id if s else None

    def get_or_create(self, face_id: str, name: str = "") -> ConversationSession:
        if face_id not in self._sessions:
            self._sessions[face_id] = ConversationSession(face_id, name)
        return self._sessions[face_id]

    def activate(self, face_id: str) -> ConversationSession:
        session = self.get_or_create(face_id)
        self._active_session_id = face_id
        session.touch()
        return session

    def deactivate(self):
        self._active_session_id = None

    def has_active_session(self) -> bool:
        return self.active_session is not None

    def is_owner(self, face_id: str) -> bool:
        return self._active_session_id == face_id

    def clear_stale(self):
        now = time.time()
        stale = [fid for fid, s in self._sessions.items()
                 if (now - s.last_activity) > SESSION_IDLE_TIMEOUT]
        for fid in stale:
            if self._active_session_id == fid:
                self._active_session_id = None
            del self._sessions[fid]

    def get_session(self, face_id: str) -> ConversationSession | None:
        return self._sessions.get(face_id)

    def end_session(self, face_id: str):
        if self._active_session_id == face_id:
            self._active_session_id = None
        self._sessions.pop(face_id, None)
