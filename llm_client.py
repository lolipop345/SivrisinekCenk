from typing import Optional

from openai import AsyncOpenAI


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str):
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._model = model

    async def complete(
        self,
        messages: list[dict],
        *,
        tools: Optional[list[dict]] = None,
        return_message: bool = False,
    ):
        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            kwargs["tools"] = tools
        response = await self._client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        if return_message:
            return msg
        return (msg.content or "").strip()

    async def aclose(self) -> None:
        await self._client.close()
