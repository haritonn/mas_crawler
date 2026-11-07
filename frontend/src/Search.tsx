import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowRight, ChevronDown, FileSearch, Search } from "lucide-react";
import { api, hostname, type Hit, type Run } from "./api";
import { Empty, ErrorMessage, ExternalLink, Spinner } from "./ui";
import { DensePanel, denseAvailable, useRetrieval } from "./Retrieval";
import { experiment, ExperimentFields, validExperiment } from "./ExperimentFields";

export function HitDiagnostics({ hit }: { hit: Hit }) {
  return <div className="hit-diagnostics mono">
    <span>BM25 rank: {hit.sparse_rank ?? "—"} · score: {hit.sparse_score ?? "—"}</span>
    <span>Dense rank: {hit.dense_rank ?? "—"} · score: {hit.dense_score ?? "—"}</span>
    {hit.chunk_position != null && <span>Чанк: {hit.chunk_position}</span>}
  </div>;
}
export function SearchPage({ run }: { run: Run }) {
  const retrieval = useRetrieval(run.id);
  const ready = denseAvailable(retrieval);
  const [config, setConfig] = useState(experiment);
  const [topK, setTopK] = useState(10);
  const [input, setInput] = useState("");
  const [result, setResult] = useState<{ query: string; hits: Hit[]; mode: string; dense_build_id: string | null; elapsed: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const canSearch = !!run.components?.index && (config.mode === "bm25" || ready) && validExperiment(config);
  async function search(event: FormEvent) {
    event.preventDefault();
    if (!input.trim() || !canSearch) return;
    controller.current?.abort();
    const abort = new AbortController(); controller.current = abort;
    const started = performance.now(), query = input.trim();
    setBusy(true); setError(""); setExpanded(null); setResult(null);
    try {
      const response = await api<{ hits: Hit[]; mode: string; dense_build_id: string | null }>(`/runs/${encodeURIComponent(run.id)}/search`, { method: "POST", signal: abort.signal, body: JSON.stringify({ query, top_k: topK, config }) });
      if (!abort.signal.aborted) setResult({ ...response, query, elapsed: Math.round(performance.now() - started) });
    } catch (e) { if (!abort.signal.aborted) setError((e as Error).message); }
    finally { if (!abort.signal.aborted) setBusy(false); }
  }
  return <>
    <section className="search-surface panel">
      <div className="search-intro"><span className="search-symbol"><FileSearch size={30} strokeWidth={1.3} /></span><h2>Поиск по корпусу</h2></div>
      {!run.components?.index && <p className="notice">Сначала нужен поисковый индекс.</p>}
      <form onSubmit={search}>
        <div className="search-settings">
          <ExperimentFields value={config} onChange={setConfig} denseReady={ready} modeLabel="Режим поиска" disabled={busy} />
          <label className="retrieval-label">Количество результатов<input type="number" min={1} max={100} required value={topK} onChange={e => setTopK(Number(e.target.value))} disabled={busy} /></label>
        </div>
        <div className="search-form"><Search size={20} /><input autoFocus aria-label="Поисковый запрос" value={input} maxLength={1000} onChange={e => setInput(e.target.value)} placeholder="Что вы хотите найти?" required /><button className="button primary" aria-label={busy ? "Ищем…" : "Найти"} disabled={busy || !input.trim() || !canSearch}>{busy ? <Spinner /> : <ArrowRight size={18} />}<span>{busy ? "Ищем…" : "Найти"}</span></button></div>
      </form>
      {config.mode !== "bm25" && !ready && <p className="notice">Поиск недоступен: нет готового dense или соединения с Qdrant. Можно выбрать BM25.</p>}

    </section>
    {error && <ErrorMessage message={error} />}
    {busy && <div className="loading-state"><Spinner />Ищем в корпусе…</div>}
    {!busy && !result && !error && <Empty icon={<Search size={26} />} title="Введите запрос" />}
    {!busy && result && <>
      <div className="section-heading result-heading"><h2>{result.hits.length ? `Результаты для «${result.query}»` : "Ничего не найдено"}</h2><span className="mono muted">{result.mode.toUpperCase()} · {result.hits.length} результатов · {result.elapsed} ms</span></div>

      {!result.hits.length ? <div className="panel"><Empty icon={<FileSearch size={26} />} title="Попробуйте другую формулировку" /></div> : <div className="search-results">{result.hits.map((hit, i) => <article className="search-result panel" key={`${hit.url}/${i}`}>
        <span className="result-rank mono">{String(i + 1).padStart(2, "0")}</span>
        <div className="result-content"><ExternalLink url={hit.url}>{hostname(hit.url)}</ExternalLink><h3><ExternalLink url={hit.url}>{hit.title || hit.url}</ExternalLink></h3><p className={expanded === hit.url ? "result-excerpt expanded" : "result-excerpt"}>{hit.text || "Предпросмотр текста недоступен."}</p>
          {expanded === hit.url && result.mode === "hybrid" && <HitDiagnostics hit={hit} />}
          <button className="text-button" onClick={() => setExpanded(expanded === hit.url ? null : hit.url)}>{expanded === hit.url ? "Свернуть" : "Читать фрагмент"}<ChevronDown size={13} className={expanded === hit.url ? "rotate" : ""} /></button></div>
        <span className="score mono">{hit.score.toFixed(3)}<small>score</small></span>
      </article>)}</div>}
    </>}
    <DensePanel run={run} resource={retrieval} />
  </>;
}
