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
export type Hit = { url: string; title: string; score: number; text: string };
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
