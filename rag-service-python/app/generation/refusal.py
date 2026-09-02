"""拒答策略（详设 §5.5 冻结）——前置敏感词 + 后置无效引用"""

from __future__ import annotations

from app.retrieval.base import ScoredChunk

SENSITIVE_TERMS = {"密码", "密钥", "token", "cookie", "secret", "生产数据库密码", "accesskey"}


class RefusalPolicy:
    """前置 + 后置两道拒答防线"""

    def __init__(self, score_threshold: float = 0.15) -> None:
        self.score_threshold = score_threshold

    def pre_refusal(self, question: str, contexts: list[ScoredChunk]) -> tuple[bool, str | None]:
        """前置拒答——检索完成后、LLM 调用前"""
        lower = question.lower()
        for term in SENSITIVE_TERMS:
            if term.lower() in lower:
                return True, f"问题包含敏感词，拒绝回答"
        if not contexts:
            return True, "未检索到相关文档片段"
        if contexts[0].score < self.score_threshold:
            return True, f"最高相关性分数 {contexts[0].score:.3f} 低于阈值 {self.score_threshold}"
        return False, None

    def post_refusal(self, citations_valid: bool) -> tuple[bool, str | None]:
        """后置拒答——LLM 生成后、返回给用户前"""
        if not citations_valid:
            return True, "所有引用验证失败，答案不可信"
        return False, None
