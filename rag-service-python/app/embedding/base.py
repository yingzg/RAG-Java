from typing import Protocol


class EmbeddingClient(Protocol):
    """Embedding 客户端协议（详设 §5.1 冻结）"""

    @property
    def model(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量向量化文档"""
        ...

    def embed_query(self, text: str) -> list[float]:
        """单条向量化用户问题"""
        ...
