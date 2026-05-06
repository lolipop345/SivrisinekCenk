from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

log = logging.getLogger("memory")


@dataclass(frozen=True)
class ExtractedFact:
    scope: Literal["user", "channel"]
    target_id: int
    fact: str


class MemoryManager:
    def __init__(
        self,
        palace_path: Path,
        llm,
        extract_prompt: str,
        retrieval_k: int = 3,
        min_fact_len: int = 6,
    ):
        self._palace_path = str(palace_path)
        self._llm = llm
        self._extract_prompt = extract_prompt
        self._k = retrieval_k
        self._min_fact_len = min_fact_len
        self._init_lock = asyncio.Lock()
        self._initialized = False
        self._last_extract_idx: dict[int, int] = {}
        self._extract_locks: dict[int, asyncio.Lock] = {}

    async def _ensure_init(self):
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            os.environ.setdefault("MEMPALACE_PALACE_PATH", self._palace_path)
            from mempalace.mcp_server import (
                tool_add_drawer,
                tool_delete_drawer,
                tool_list_drawers,
            )
            from mempalace.searcher import search_memories

            self._tool_add = tool_add_drawer
            self._tool_search = search_memories
            self._tool_list = tool_list_drawers
            self._tool_delete = tool_delete_drawer
            self._initialized = True

    @staticmethod
    def _user_wing(user_id: int) -> str:
        return f"user_{int(user_id)}"

    @staticmethod
    def _channel_wing(channel_id: int) -> str:
        return f"channel_{int(channel_id)}"

    async def add_user_fact(self, user_id: int, fact: str, source: str = "manual"):
        return await self._add(self._user_wing(user_id), fact, source)

    async def add_channel_fact(self, channel_id: int, fact: str, source: str = "manual"):
        return await self._add(self._channel_wing(channel_id), fact, source)

    async def _add(self, wing: str, fact: str, source: str):
        fact = fact.strip()
        if len(fact) < self._min_fact_len:
            return None
        await self._ensure_init()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._tool_add(
                wing=wing,
                room="facts",
                content=fact,
                source_file=source,
                added_by="sivrisinekcenk",
            ),
        )

    async def query_relevant(
        self, user_id: int, channel_id: int, query: str
    ) -> list[str]:
        if not query.strip():
            return []
        await self._ensure_init()
        loop = asyncio.get_running_loop()
        results = await asyncio.gather(
            loop.run_in_executor(
                None,
                lambda: self._tool_search(
                    query=query,
                    palace_path=self._palace_path,
                    wing=self._user_wing(user_id),
                    room="facts",
                    n_results=self._k,
                ),
            ),
            loop.run_in_executor(
                None,
                lambda: self._tool_search(
                    query=query,
                    palace_path=self._palace_path,
                    wing=self._channel_wing(channel_id),
                    room="facts",
                    n_results=self._k,
                ),
            ),
            return_exceptions=True,
        )
        out: list[str] = []
        for res in results:
            if isinstance(res, Exception):
                log.warning("query_relevant partial fail: %s", res)
                continue
            for r in (res or {}).get("results", []) or []:
                txt = (r.get("text") or "").strip()
                if txt and txt not in out:
                    out.append(txt)
        return out

    async def _all_drawer_ids_in_wing(self, wing: str) -> list[str]:
        await self._ensure_init()
        loop = asyncio.get_running_loop()
        ids: list[str] = []
        offset = 0
        page_size = 100
        while True:
            page = await loop.run_in_executor(
                None,
                lambda o=offset: self._tool_list(
                    wing=wing, room="facts", limit=page_size, offset=o
                ),
            )
            if not isinstance(page, dict) or "drawers" not in page:
                break
            drawers = page.get("drawers") or []
            ids.extend(d["drawer_id"] for d in drawers if "drawer_id" in d)
            if len(drawers) < page_size:
                break
            offset += page_size
        return ids

    async def forget_user(self, user_id: int) -> int:
        return await self._forget_wing(self._user_wing(user_id))

    async def forget_channel(self, channel_id: int) -> int:
        return await self._forget_wing(self._channel_wing(channel_id))

    async def _forget_wing(self, wing: str) -> int:
        ids = await self._all_drawer_ids_in_wing(wing)
        if not ids:
            return 0
        loop = asyncio.get_running_loop()
        deleted = 0
        for did in ids:
            res = await loop.run_in_executor(None, self._tool_delete, did)
            if isinstance(res, dict) and res.get("success"):
                deleted += 1
        return deleted

    async def list_user_facts(self, user_id: int, limit: int = 100) -> list[str]:
        return await self._list_facts(self._user_wing(user_id), limit)

    async def list_channel_facts(self, channel_id: int, limit: int = 100) -> list[str]:
        return await self._list_facts(self._channel_wing(channel_id), limit)

    async def _list_facts(self, wing: str, limit: int) -> list[str]:
        await self._ensure_init()
        loop = asyncio.get_running_loop()
        page = await loop.run_in_executor(
            None,
            lambda: self._tool_list(wing=wing, room="facts", limit=limit, offset=0),
        )
        if not isinstance(page, dict):
            return []
        out: list[str] = []
        for d in page.get("drawers") or []:
            txt = d.get("content_preview") or ""
            if txt.endswith("..."):
                txt = txt[:-3]
            txt = txt.strip()
            if txt:
                out.append(txt)
        return out

    async def maybe_auto_extract(
        self,
        channel_id: int,
        author_id: int,
        snapshot: list[dict],
        every_n: int,
    ):
        user_count = sum(1 for m in snapshot if m.get("role") == "user")
        last = self._last_extract_idx.get(channel_id, 0)
        if user_count - last < every_n:
            return
        lock = self._extract_locks.setdefault(channel_id, asyncio.Lock())
        if lock.locked():
            return
        async with lock:
            self._last_extract_idx[channel_id] = user_count
            try:
                facts = await self._extract(snapshot, channel_id, author_id)
            except Exception as e:
                log.warning("auto_extract LLM call failed: %s", e)
                return
            for f in facts:
                try:
                    if f.scope == "user":
                        await self.add_user_fact(f.target_id, f.fact, source="auto")
                    elif f.scope == "channel":
                        await self.add_channel_fact(f.target_id, f.fact, source="auto")
                except Exception as e:
                    log.warning("auto_extract write fail (%s/%s): %s", f.scope, f.target_id, e)

    async def _extract(
        self, snapshot: list[dict], channel_id: int, author_id: int
    ) -> list[ExtractedFact]:
        recent = [m for m in snapshot if m.get("role") in ("user", "assistant")][-20:]
        flat: list[dict] = []
        for m in recent:
            c = m["content"]
            if isinstance(c, list):
                c = " ".join(p.get("text", "") for p in c if p.get("type") == "text")
            flat.append({"role": m["role"], "content": c})
        ctx = (
            f"Bu kanalın Discord ID'si: {channel_id}\n"
            f"Bu turn'de yazan kullanıcının Discord ID'si: {author_id}\n"
            "user scope için target_id = kullanıcı ID'si, "
            "channel scope için = kanal ID'si."
        )
        msgs = [
            {"role": "system", "content": self._extract_prompt + "\n\n" + ctx},
            *flat,
        ]
        raw = await self._llm.complete(msgs)
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        out: list[ExtractedFact] = []
        for d in data:
            try:
                scope = d["scope"]
                if scope not in ("user", "channel"):
                    continue
                fact = str(d["fact"]).strip()
                if len(fact) < self._min_fact_len:
                    continue
                out.append(
                    ExtractedFact(
                        scope=scope,
                        target_id=int(d["target_id"]),
                        fact=fact,
                    )
                )
            except (KeyError, ValueError, TypeError):
                continue
        return out
