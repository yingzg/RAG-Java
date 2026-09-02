from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from app.models import (
    AnswerRequest,
    AnswerResponse,
    DocumentUploadResponse,
    EvalRunRequest,
    EvalRunResponse,
    HealthResponse,
    IncrementalIndexRequest,
    IncrementalIndexResponse,
    IndexRebuildRequest,
    IndexRebuildResponse,
    SearchRequest,
    SearchResponse,
    TraceResponse,
)
from app.service import RagApplicationService
from app.settings import Settings

settings = Settings()
rag_service = RagApplicationService(settings=settings)

app = FastAPI(
    title="RAG Knowledge Service",
    version="0.2.0",
    description="Independent RAG service for knowledge retrieval, answer generation, trace, and eval.",
    docs_url="/docs",
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.get("/", response_class=HTMLResponse)
def index():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>RAG Knowledge Service</h1><p>Frontend not found.</p>")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="rag-service-python")


@app.post("/api/v1/index/rebuild", response_model=IndexRebuildResponse)
def rebuild_index(request: IndexRebuildRequest) -> IndexRebuildResponse:
    return rag_service.rebuild_index(request)


@app.post("/api/v1/index/incremental", response_model=IncrementalIndexResponse)
def incremental_index(request: IncrementalIndexRequest) -> IncrementalIndexResponse:
    return rag_service.incremental_index(request)


@app.post("/api/v1/documents/upload", response_model=DocumentUploadResponse)
async def upload_documents(
    category: str = Form(...),
    files: list[UploadFile] = File(...),
) -> DocumentUploadResponse:
    file_data = [(f.filename or "", await f.read()) for f in files]
    return rag_service.upload_documents(category, file_data)


@app.post("/api/v1/search", response_model=SearchResponse)
def search(request: SearchRequest) -> SearchResponse:
    try:
        return rag_service.search(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/v1/answer", response_model=AnswerResponse)
def answer(request: AnswerRequest) -> AnswerResponse:
    try:
        return rag_service.answer(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/v1/traces/{trace_id}", response_model=TraceResponse)
def get_trace(trace_id: str) -> TraceResponse:
    trace = rag_service.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"trace not found: {trace_id}")
    return trace


@app.post("/api/v1/eval/run", response_model=EvalRunResponse)
def run_eval(request: EvalRunRequest) -> EvalRunResponse:
    return rag_service.run_eval(request)
