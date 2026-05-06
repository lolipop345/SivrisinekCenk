from openai import AsyncOpenAI


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str):
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._model = model

    async def complete(self, messages: list[dict]) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            stream=False,
        )
        content = response.choices[0].message.content or ""
        return content.strip()

    async def aclose(self) -> None:
        await self._client.close()
