from __future__ import annotations

import json
import time
from pathlib import Path

from app.retrieval.base import QueryTokenizer
from app.retrieval.keyword import KeywordRetriever


class EvalCase:
    def __init__(self, data: dict):
        self.id: str = data["id"]
        self.question: str = data["question"]
        self.expected_source_name: str | None = data.get("expected_source_name")
        self.expected_sources: list[str] = data.get("expected_sources", [])
        self.expected_answer_points: list[str] = data.get("expected_answer_points", [])
        self.should_refuse: bool = data.get("should_refuse", False)
        self.risk: str = data.get("risk", "normal")


class EvalResult:
    def __init__(self, case_id: str):
        self.case_id = case_id
        self.retrieval_hit = False
        self.recall_at_5 = False
        self.recall_at_10 = False
        self.mrr = 0.0
        self.top1_source = ""
        self.top5_sources: list[str] = []
        self.refusal_correct: bool | None = None
        self.latency_ms = 0
        self.error_type: str | None = None


class EvalReport:
    def __init__(self, results: list[EvalResult]):
        self.results = results
        self.total = len(results)
        self.retrieval_hit_count = sum(1 for r in results if r.retrieval_hit)
        self.refusal_total = sum(1 for r in results if r.refusal_correct is not None)
        self.refusal_correct_count = sum(1 for r in results if r.refusal_correct is True)
        self.mrr = sum(r.mrr for r in results) / max(self.total, 1)
        recall_cases = [r for r in results if not r.error_type]
        self.recall_at_5 = sum(1 for r in recall_cases if r.recall_at_5) / max(len(recall_cases), 1)
        self.pass_rate = self.retrieval_hit_count / max(self.total, 1)
        self.refusal_correct_rate = self.refusal_correct_count / max(self.refusal_total, 1) if self.refusal_total else 0.0
        self.bad_cases = [r for r in results if r.error_type or (not r.recall_at_5 and not r.refusal_correct)]

    def to_markdown(self) -> str:
        lines = [
            "# RAG Eval Report",
            "",
            f"总用例: {self.total}",
            f"检索命中 (Recall@5): {self.retrieval_hit_count}/{self.total} ({self.recall_at_5:.1%})",
            f"MRR: {self.mrr:.3f}",
            f"拒答正确率: {self.refusal_correct_count}/{self.refusal_total} ({self.refusal_correct_rate:.1%})",
            f"综合通过率: {self.pass_rate:.1%}",
            "",
            "## 明细",
            "",
            "| ID | Recall@5 | MRR | Top-1 Source | 拒答正确 | 延迟(ms) | 错误 |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in self.results:
            refusal = "N/A" if r.refusal_correct is None else ("✅" if r.refusal_correct else "❌")
            error = r.error_type or ""
            lines.append(f"| {r.case_id} | {'✅' if r.recall_at_5 else '❌'} | {r.mrr:.3f} | {r.top1_source} | {refusal} | {r.latency_ms} | {error} |")
        if self.bad_cases:
            lines.append("")
            lines.append("## Bad Cases")
            for bc in self.bad_cases:
                lines.append(f"- **{bc.case_id}**: recall={bc.recall_at_5}, error={bc.error_type or 'low recall'}")
        return "\n".join(lines)


class EvalRunner:
    def __init__(self, retriever: KeywordRetriever, chunk_store, cases_path: Path):
        self._retriever = retriever
        self._chunk_store = chunk_store
        self._cases_path = cases_path

    def run(self, top_k: int = 5) -> EvalReport:
        cases = self._load_cases()
        results: list[EvalResult] = []
        for case in cases:
            r = self._eval_one(case, top_k)
            results.append(r)
        return EvalReport(results)

    def _eval_one(self, case: EvalCase, top_k: int) -> EvalResult:
        started = time.perf_counter()
        result = EvalResult(case.id)
        try:
            chunks = self._chunk_store.load()
            scored = self._retriever.search(chunks, case.question, top_k=10, filters=None)
            result.latency_ms = int((time.perf_counter() - started) * 1000)
            top5 = scored[:5]
            result.top5_sources = [s.chunk.source_name for s in top5]
            result.top1_source = result.top5_sources[0] if result.top5_sources else ""
            if case.expected_source_name:
                result.recall_at_5 = case.expected_source_name in result.top5_sources
                result.recall_at_10 = case.expected_source_name in [s.chunk.source_name for s in scored[:10]]
                result.retrieval_hit = result.recall_at_5
                for rank, s in enumerate(scored, start=1):
                    if s.chunk.source_name == case.expected_source_name:
                        result.mrr = 1.0 / rank
                        break
            if case.should_refuse:
                result.refusal_correct = not result.recall_at_5 or result.mrr < 0.1
        except Exception as e:
            result.error_type = type(e).__name__
        return result

    def _load_cases(self) -> list[EvalCase]:
        cases = []
        for line in self._cases_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            cases.append(EvalCase(json.loads(line)))
        return cases
