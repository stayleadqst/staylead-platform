"""Azure OpenAI adapter boundary; deliberately performs no network requests yet."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AzureOpenAIConfig:
    base_url: str
    api_key: str
    model_deployment: str


class AzureOpenAIProvider:
    """Reserved adapter seam. Calling it fails explicitly until transport is implemented."""

    def __init__(self, config: AzureOpenAIConfig) -> None:
        self._config = config

    async def generate(self, *, instructions: str, input_text: str) -> str:
        raise NotImplementedError(
            "Azure OpenAI transport is not implemented in this source skeleton."
        )
