from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    service: str


class SearchFilters(BaseModel):
    source_name: str | None = None
    doc_type: str | None = None
    project: str | None = None
    version: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    mode: str = "hybrid"
    rerank: bool = True
    include_content: bool = True


class SearchHit(BaseModel):
    chunk_id: str
    score: float
    source_name: str
    source_path: str
    section_path: str
    doc_type: str
    matched_terms: list[str] = []
    keyword_score: float = 0.0
    vector_score: float = 0.0
    rerank_score: float | None = None
    retriever: str = ""
    content: str | None = None


class SearchResponse(BaseModel):
    trace_id: str
    query: str
    results: list[SearchHit]
    latency_ms: int


class AnswerRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    require_citation: bool = True
    allow_refusal: bool = True


class Citation(BaseModel):
    chunk_id: str
    source_name: str
    source_path: str
    section_path: str


class AnswerResponse(BaseModel):
    trace_id: str
    question: str
    refused: bool
    refusal_reason: str | None = None
    answer: str
    citations: list[Citation]
    tokens: dict = {}
    latency_ms: int


class IndexRebuildRequest(BaseModel):
    source_names: list[str] = Field(default_factory=list)
    mode: str = "full"


class IndexRebuildResponse(BaseModel):
    job_id: str
    status: str
    message: str
    document_count: int = 0
    chunk_count: int = 0


class TraceResponse(BaseModel):
    trace_id: str
    payload: dict


class EvalRunRequest(BaseModel):
    case_set: str = "day1"
    top_k: int = Field(default=5, ge=1, le=20)


class EvalRunResponse(BaseModel):
    report_id: str
    total: int
    passed: int
    failed: int
    pass_rate: float
    recall_at_5: float = 0.0
    mrr: float = 0.0
    refusal_correct_rate: float = 0.0
    message: str


class DocumentUploadResponse(BaseModel):
    uploaded: list[str] = []
    failed: list[dict] = []


class IncrementalIndexRequest(BaseModel):
    source_names: list[str] = Field(default_factory=list)


class IncrementalIndexResponse(BaseModel):
    job_id: str
    new_documents: int = 0
    changed_documents: int = 0
    deleted_documents: int = 0
    new_chunks: int = 0
    deleted_chunks: int = 0
    latency_ms: int = 0
    message: str = ""
