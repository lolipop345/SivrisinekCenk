import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class Session:
    messages: list[dict]
    last_activity: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class SessionStore:
    def __init__(self, ttl_seconds: int, max_messages: int, system_prompt: str):
        self._ttl = ttl_seconds
        self._max_messages = max_messages
        self._system_prompt = system_prompt
        self._sessions: dict[int, Session] = {}
        self._dict_lock = asyncio.Lock()

    def _new_session(self) -> Session:
        return Session(
            messages=[{"role": "system", "content": self._system_prompt}],
            last_activity=time.monotonic(),
        )

    async def get_or_create(self, channel_id: int) -> Session:
        async with self._dict_lock:
            session = self._sessions.get(channel_id)
            if session is None or time.monotonic() - session.last_activity > self._ttl:
                session = self._new_session()
                self._sessions[channel_id] = session
            return session

    async def append(self, channel_id: int, role: str, content: str) -> None:
        session = self._sessions.get(channel_id)
        if session is None:
            return
        session.messages.append({"role": role, "content": content})
        session.last_activity = time.monotonic()
        while len(session.messages) > self._max_messages:
            del session.messages[1]

    async def clear(self, channel_id: int) -> None:
        async with self._dict_lock:
            self._sessions.pop(channel_id, None)

    async def snapshot(self, channel_id: int) -> list[dict]:
        session = self._sessions.get(channel_id)
        if session is None:
            return [{"role": "system", "content": self._system_prompt}]
        return list(session.messages)
