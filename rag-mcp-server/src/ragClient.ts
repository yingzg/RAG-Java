import { RAG_SERVICE_BASE_URL } from "./config.js";

export type SearchInput = {
  query: string;
  domain?: "dubbo" | "ddd" | "state-machine" | "bff" | "notes" | "rag-knowledge";
  doc_type?: string;
  project?: string;
  version?: string;
  top_k?: number;
  mode?: "keyword" | "vector" | "hybrid";
  rerank?: boolean;
};

export type AnswerInput = {
  question: string;
  domain?: string;
  top_k?: number;
  require_citation?: boolean;
  allow_refusal?: boolean;
};

export type EvalRunInput = {
  case_set?: string;
  top_k?: number;
};

export type SearchHit = {
  chunk_id: string;
  score: number;
  source_name: string;
  source_path: string;
  section_path: string;
  doc_type: string;
  matched_terms: string[];
  keyword_score: number;
  vector_score: number;
  rerank_score: number | null;
  retriever: string;
  content: string | null;
};

export type SearchResponse = {
  trace_id: string;
  query: string;
  results: SearchHit[];
  latency_ms: number;
};

export type Citation = {
  chunk_id: string;
  source_name: string;
  source_path: string;
  section_path: string;
};

export type AnswerResponse = {
  trace_id: string;
  question: string;
  refused: boolean;
  refusal_reason: string | null;
  answer: string;
  citations: Citation[];
  tokens: Record<string, number>;
  latency_ms: number;
};

export type EvalRunResponse = {
  report_id: string;
  total: number;
  passed: number;
  failed: number;
  pass_rate: number;
  recall_at_5: number;
  mrr: number;
  refusal_correct_rate: number;
  message: string;
};

export class RagClient {
  async search(input: SearchInput): Promise<SearchResponse> {
    return this.post("/api/v1/search", {
      query: input.query,
      top_k: input.top_k ?? 5,
      mode: input.mode ?? "hybrid",
      rerank: input.rerank ?? true,
      filters: {
        source_name: input.domain,
        doc_type: input.doc_type,
        project: input.project,
        version: input.version,
      },
      include_content: true,
    }) as Promise<SearchResponse>;
  }

  async answer(input: AnswerInput): Promise<AnswerResponse> {
    return this.post("/api/v1/answer", {
      question: input.question,
      top_k: input.top_k ?? 5,
      filters: { source_name: input.domain },
      require_citation: input.require_citation ?? true,
      allow_refusal: input.allow_refusal ?? true,
    }) as Promise<AnswerResponse>;
  }

  async runEval(input: EvalRunInput): Promise<EvalRunResponse> {
    return this.post("/api/v1/eval/run", {
      case_set: input.case_set ?? "full",
      top_k: input.top_k ?? 5,
    }) as Promise<EvalRunResponse>;
  }

  private async post(path: string, body: unknown): Promise<unknown> {
    const response = await fetch(`${RAG_SERVICE_BASE_URL}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`RAG service request failed: ${response.status} ${text}`);
    }
    return response.json();
  }
}
