export type View =
  "overview" | "sources" | "documents" | "annotation" | "search" | "evaluation";
export type Package = {
  id: string;
  pairs: number;
  labeled: number;
  accepted: boolean;
  label_source: string | null;
};
export type Run = {
  id: string;
  name: string;
  url: string;
  goal: string;
  status: "running" | "ready" | "failed" | "interrupted" | "collected";
  stage: "analyze" | "crawl" | "index" | "annotation" | "ready";
  documents: number;
  pairs: number;
  labeled: number;
  created_at: string;
  error: string | null;
  packages: Package[];
  archived: boolean;
  components: { plan: boolean; corpus: boolean; index: boolean };
};
export type Pair = {
  pair_id: string;
  query_id: string;
  query: string;
  document_url: string;
  document_title: string;
  document_text: string;
  relevance: number | null;
};
export type Hit = {
  url: string; title: string; score: number; text: string;
  sparse_rank?: number | null; dense_rank?: number | null;
  sparse_score?: number | null; dense_score?: number | null; chunk_position?: number | null;
};
export type RetrievalExperiment = {
  name: string; mode: "bm25" | "dense" | "hybrid";
  sparse_config: { title_weight: number; text_weight: number };
  sparse_top_k: number; dense_top_k: number;
  sparse_weight: number; dense_weight: number; rrf_k: number;
};
export type RetrievalJob = {
  id: string; kind: "dense" | "evaluation";
  status: "running" | "ready" | "failed" | "interrupted";
  stage: string; completed: number; total: number | null;
  created_at: string; error: string | null; package?: string; top_k?: number;
};
export type DenseProfile = {
  model_id: string; normalize_embeddings?: boolean; query_prompt?: string | null;
  document_prompt?: string | null; max_seq_length?: number | null;
  similarity?: "cosine" | "dot" | "euclidean";
};
export type RetrievalState = {
  dense: {
    status: "absent" | RetrievalJob["status"]; ready: boolean;
    job: RetrievalJob | null; profile: DenseProfile | null;
    documents: number; chunks: number; build_id: string | null;
    error?: string | null;
  };
  qdrant: { available: boolean; error: string | null };
  active_job: RetrievalJob | null;
};
export type RetrievalReport = {
  name: string; config: Omit<RetrievalExperiment, "name">;
  evaluation: { aggregate: Record<string, number>; per_query: Record<string, Record<string, number>> };
  results: Record<string, Hit[]>;
  timing: Record<string, number | string>;
};
export type EvaluationReport = {
  id: string; created_at: string; package: string; split: "dev";
  label_source: string | null; top_k: number; corpus_documents: number;
  dense_build_id: string | null; queries: Record<string, string>;
  qrels: Record<string, Record<string, number>>; reports: RetrievalReport[];
};
export type Report = {
  name: string;
  config: { title_weight: number; text_weight: number };
  evaluation: {
    aggregate: Record<string, number>;
    per_query: Record<string, Record<string, number>>;
  };
};

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message =
      typeof body?.detail === "string"
        ? body.detail
        : `Не удалось выполнить запрос (${response.status}).`;
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export function packageQuery(id: string) {
  return `?package=${encodeURIComponent(id)}`;
}
export function hostname(url: string) {
  try {
    return new URL(url).hostname;
  } catch {
    return url || "Локальный корпус";
  }
}
export function sourceName(run: Run) {
  return run.name && run.name !== run.id ? run.name : hostname(run.url);
}
export function safeUrl(url: string) {
  try {
    const parsed = new URL(url);
    return ["http:", "https:"].includes(parsed.protocol)
      ? parsed.href
      : undefined;
  } catch {
    return undefined;
  }
}
export const number = (value: number) =>
  new Intl.NumberFormat("ru-RU").format(value);
