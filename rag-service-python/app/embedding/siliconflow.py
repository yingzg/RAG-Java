from __future__ import annotations

import httpx

from app.settings import Settings


class SiliconFlowEmbeddingClient:
    """SiliconFlow（硅基流动）Embedding 客户端 — BAAI/bge-m3（详设 §5.1）"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = settings.embedding_model
        self._dimension = settings.embedding_dim

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        all_embeddings: list[list[float]] = []
        batch_size = self._settings.embedding_batch_size
        base_url = self._settings.embedding_base_url
        api_key = self._settings.embedding_api_key

        with httpx.Client(timeout=httpx.Timeout(30.0), proxy=None) as client:
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                response = client.post(
                    f"{base_url}/embeddings",
                    json={"model": self._model, "input": batch},
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                data = response.json()
                all_embeddings.extend(
                    [item["embedding"] for item in data["data"]]
                )
        return all_embeddings

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
