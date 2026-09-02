from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.embedding.siliconflow import SiliconFlowEmbeddingClient

PROJECT_ROOT = Path(__file__).parent.parent
EVAL_CASES_PATH = PROJECT_ROOT / "eval" / "rag_cases.jsonl"

from app.eval.runner import EvalRunner
from app.generation.answer_generator import AnswerGenerator
from app.generation.citation import CitationValidator
from app.generation.llm import DeepSeekLlmClient
from app.generation.prompt_builder import PromptBuilder
from app.generation.refusal import RefusalPolicy
from app.ingestion.index_service import IndexService
from app.models import (
    AnswerRequest,
    AnswerResponse,
    Citation,
    DocumentUploadResponse,
    EvalRunRequest,
    EvalRunResponse,
    IncrementalIndexRequest,
    IncrementalIndexResponse,
    IndexRebuildRequest,
    IndexRebuildResponse,
    SearchHit,
    SearchRequest,
    SearchResponse,
    TraceResponse,
)
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.keyword import KeywordRetriever
from app.retrieval.reranker import RuleBasedReranker
from app.retrieval.vector import VectorRetriever
from app.settings import Settings
from app.store.chunk_store import JsonlChunkStore
from app.store.vector_store import LocalVectorStore

ALLOWED_UPLOAD_SUFFIXES = {".md", ".txt"}


class RagApplicationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.chunk_store = JsonlChunkStore(settings.chunk_index_path)
        self.vector_store = LocalVectorStore(settings.vector_index_path)
        self.embedding_client = SiliconFlowEmbeddingClient(settings)
        self.keyword_retriever = KeywordRetriever()
        self.vector_retriever = VectorRetriever(self.embedding_client, self.vector_store, self.chunk_store)
        self.hybrid_retriever = HybridRetriever(self.keyword_retriever, self.vector_retriever)
        self.reranker = RuleBasedReranker()
        self.index_service = IndexService(settings, self.embedding_client, self.chunk_store, self.vector_store)
        self.llm_client = DeepSeekLlmClient(settings)
        self.prompt_builder = PromptBuilder()
        self.answer_generator = AnswerGenerator(self.llm_client, self.prompt_builder)
        self.citation_validator = CitationValidator()
        self.refusal_policy = RefusalPolicy(settings.refuse_score_threshold)
        self.eval_runner = EvalRunner(self.keyword_retriever, self.chunk_store, EVAL_CASES_PATH)

    # ── Index ──

    def rebuild_index(self, request: IndexRebuildRequest) -> IndexRebuildResponse:
        trace = self.index_service.rebuild(request.source_names or None)
        return IndexRebuildResponse(
            job_id=trace["trace_id"],
            status="completed",
            message=f"indexed {trace['document_count']} documents, {trace['chunk_count']} chunks in {trace['latency_ms']}ms",
            document_count=trace["document_count"],
            chunk_count=trace["chunk_count"],
        )

    def incremental_index(self, request: IncrementalIndexRequest) -> IncrementalIndexResponse:
        trace = self.index_service.incremental(request.source_names or None)
        return IncrementalIndexResponse(
            job_id=trace["trace_id"],
            new_documents=trace["new_documents"],
            changed_documents=trace["changed_documents"],
            deleted_documents=trace["deleted_documents"],
            new_chunks=trace["new_chunks"],
            deleted_chunks=trace["deleted_chunks"],
            latency_ms=trace["latency_ms"],
            message=(
                f"新增 {trace['new_documents']} 文档, "
                f"变更 {trace['changed_documents']} 文档, "
                f"删除 {trace['deleted_documents']} 文档, "
                f"新增 {trace['new_chunks']} chunks"
            ),
        )

    def upload_documents(self, category: str, files: list[tuple[str, bytes]]) -> DocumentUploadResponse:
        """上传文档到指定知识源目录，返回成功/失败列表。"""
        target_dir = self.settings.category_dirs.get(category)
        if target_dir is None:
            return DocumentUploadResponse(failed=[{"error": f"未知分类: {category}"}])

        target_path = Path(target_dir)
        uploaded: list[str] = []
        failed: list[dict] = []

        for filename, content in files:
            if Path(filename).suffix.lower() not in ALLOWED_UPLOAD_SUFFIXES:
                failed.append({"filename": filename, "error": "不支持的文件类型，仅支持 .md/.txt"})
                continue
            if not filename or "/" in filename or "\\" in filename or ".." in filename:
                failed.append({"filename": filename, "error": "非法文件名"})
                continue
            try:
                (target_path / filename).write_bytes(content)
                uploaded.append(filename)
            except Exception as exc:
                failed.append({"filename": filename, "error": str(exc)})

        return DocumentUploadResponse(uploaded=uploaded, failed=failed)

    # ── Search ──

    def search(self, request: SearchRequest) -> SearchResponse:
        started = time.perf_counter()
        chunks = self.chunk_store.load()

        if request.mode == "keyword":
            results = self.keyword_retriever.search(chunks, request.query, request.top_k, request.filters)
        elif request.mode == "vector":
            results = self.vector_retriever.search(request.query, request.top_k)
        else:
            results = self.hybrid_retriever.search(chunks, request.query, request.top_k, request.filters)

        if request.rerank and request.mode != "keyword":
            results = self.reranker.rerank(request.query, results, top_n=min(request.top_k, len(results)))

        trace_id = self._new_trace_id()
        response = SearchResponse(
            trace_id=trace_id,
            query=request.query,
            results=[self._to_search_hit(item, request.include_content) for item in results],
            latency_ms=self._elapsed_ms(started),
        )
        self._write_trace(trace_id, {"type": "search", "request": request.model_dump(), "response": response.model_dump()})
        return response

    # ── Answer（LLM 全链路） ──

    def answer(self, request: AnswerRequest) -> AnswerResponse:
        started = time.perf_counter()
        chunks = self.chunk_store.load()

        # Step 1: 检索
        raw_results = self.hybrid_retriever.search(chunks, request.question, request.top_k, request.filters)
        retrieved_before_rerank = self._snapshot_results(raw_results)

        # Step 2: Rerank
        results = self.reranker.rerank(request.question, raw_results, top_n=min(self.settings.rerank_top_n, len(raw_results)))
        retrieved_after_rerank = self._snapshot_results(results)

        # Step 3: 前置拒答
        if request.allow_refusal:
            refused, refusal_reason = self.refusal_policy.pre_refusal(request.question, results)
            if refused:
                trace = self._build_answer_trace(request.question, retrieved_before_rerank, retrieved_after_rerank,
                    prompt_messages=[], llm_raw="", llm_input_tokens=0, llm_output_tokens=0,
                    refused=True, refusal_reason=refusal_reason, citations=[], elapsed_ms=self._elapsed_ms(started))
                self._write_structured_trace(trace)
                return self._refused_response(request.question, refusal_reason or "无可靠证据", started)

        # Step 4: 组装 Prompt
        prompt_messages = self.prompt_builder.build(request.question, results)
        prompt_snapshot = [{"role": m.role, "content": m.content} for m in prompt_messages]

        # Step 5: LLM 生成
        generated = self.answer_generator.answer(request.question, results)

        # Step 6: 后置引用校验
        valid_citations = self.citation_validator.validate(generated.text, results)

        # 记录所有候选引用（含未通过校验的）
        all_citation_info = []
        for item in results:
            c = item.chunk
            all_citation_info.append({
                "chunk_id": c.chunk_id, "source_name": c.source_name,
                "source_path": c.source_path, "section_path": c.section_path,
                "verified": any(vc["chunk_id"] == c.chunk_id for vc in valid_citations),
                "score": item.score, "keyword_score": item.keyword_score,
                "vector_score": item.vector_score, "rerank_score": item.rerank_score,
                "retriever": item.retriever, "match_reasons": item.match_reasons,
            })

        if request.allow_refusal and not valid_citations:
            trace = self._build_answer_trace(request.question, retrieved_before_rerank, retrieved_after_rerank,
                prompt_messages=prompt_snapshot, llm_raw=generated.text,
                llm_input_tokens=generated.input_tokens, llm_output_tokens=generated.output_tokens,
                refused=True, refusal_reason="所有引用验证失败，答案不可信",
                citations=all_citation_info, elapsed_ms=self._elapsed_ms(started))
            self._write_structured_trace(trace)
            return self._refused_response(request.question, "所有引用验证失败，答案不可信", started)

        # Step 7: 成功返回
        trace_id = self._new_trace_id()
        response = AnswerResponse(
            trace_id=trace_id, question=request.question, refused=False,
            answer=generated.text,
            citations=[Citation(**c) for c in valid_citations],
            tokens={"input": generated.input_tokens, "output": generated.output_tokens},
            latency_ms=self._elapsed_ms(started),
        )

        trace = self._build_answer_trace(request.question, retrieved_before_rerank, retrieved_after_rerank,
            prompt_messages=prompt_snapshot, llm_raw=generated.text,
            llm_input_tokens=generated.input_tokens, llm_output_tokens=generated.output_tokens,
            refused=False, refusal_reason=None,
            citations=all_citation_info, elapsed_ms=self._elapsed_ms(started))
        self._write_structured_trace(trace)
        return response

    # ── Trace ──

    def get_trace(self, trace_id: str) -> TraceResponse | None:
        path = self.settings.trace_dir / f"{trace_id}.json"
        if not path.exists():
            return None
        return TraceResponse(trace_id=trace_id, payload=json.loads(path.read_text(encoding="utf-8")))

    # ── Eval ──

    def run_eval(self, request: EvalRunRequest) -> EvalRunResponse:
        report = self.eval_runner.run(top_k=request.top_k)
        return EvalRunResponse(
            report_id=f"eval_{uuid4().hex[:12]}",
            total=report.total,
            passed=report.retrieval_hit_count,
            failed=report.total - report.retrieval_hit_count,
            pass_rate=report.pass_rate,
            recall_at_5=report.recall_at_5,
            mrr=report.mrr,
            refusal_correct_rate=report.refusal_correct_rate,
            message=report.to_markdown(),
        )

    # ── Private: Trace ──

    def _snapshot_results(self, results) -> list[dict]:
        return [{
            "chunk_id": item.chunk.chunk_id, "source_name": item.chunk.source_name,
            "source_path": item.chunk.source_path, "section_path": item.chunk.section_path,
            "score": item.score, "keyword_score": item.keyword_score,
            "vector_score": item.vector_score, "rerank_score": item.rerank_score,
            "retriever": item.retriever, "match_reasons": item.match_reasons,
        } for item in results]

    def _build_answer_trace(self, question, retrieved_before, retrieved_after, prompt_messages,
                           llm_raw, llm_input_tokens, llm_output_tokens,
                           refused, refusal_reason, citations, elapsed_ms) -> dict:
        return {
            "type": "answer",
            "question": question,
            "retrieved_before_rerank": retrieved_before,
            "retrieved_after_rerank": retrieved_after,
            "final_context_chunks": [c["chunk_id"] for c in retrieved_after],
            "prompt_messages": prompt_messages,
            "llm_raw_output": llm_raw,
            "llm_model": self.settings.llm_model,
            "llm_tokens": {"input": llm_input_tokens, "output": llm_output_tokens},
            "refused": refused,
            "refusal_reason": refusal_reason,
            "citations": citations,
            "latency_ms": elapsed_ms,
        }

    def _write_structured_trace(self, trace: dict) -> None:
        trace_id = self._new_trace_id()
        trace["trace_id"] = trace_id
        trace["created_at"] = datetime.now(timezone.utc).isoformat()
        self.settings.trace_dir.mkdir(parents=True, exist_ok=True)
        (self.settings.trace_dir / f"{trace_id}.json").write_text(
            json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _refused_response(self, question: str, reason: str, started: float) -> AnswerResponse:
        trace_id = self._new_trace_id()
        response = AnswerResponse(
            trace_id=trace_id,
            question=question,
            refused=True,
            refusal_reason=reason,
            answer=f"根据当前资料无法确认。\n\n{reason}",
            citations=[],
            latency_ms=self._elapsed_ms(started),
        )
        self._write_trace(trace_id, {"type": "answer_refused", "question": question, "reason": reason})
        return response

    def _to_search_hit(self, item, include_content: bool) -> SearchHit:
        chunk = item.chunk
        return SearchHit(
            chunk_id=chunk.chunk_id,
            score=item.score,
            source_name=chunk.source_name,
            source_path=chunk.source_path,
            section_path=chunk.section_path,
            doc_type=chunk.doc_type,
            matched_terms=item.matched_terms,
            keyword_score=item.keyword_score,
            vector_score=item.vector_score,
            rerank_score=item.rerank_score,
            retriever=item.retriever,
            content=chunk.content if include_content else None,
        )

    def _write_trace(self, trace_id: str, payload: dict) -> None:
        self.settings.trace_dir.mkdir(parents=True, exist_ok=True)
        payload["created_at"] = datetime.now(timezone.utc).isoformat()
        (self.settings.trace_dir / f"{trace_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _new_trace_id(self) -> str:
        return f"trace_{uuid4().hex[:16]}"

    def _elapsed_ms(self, started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
