import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowDown, ArrowRight, ArrowUp, ArrowUpDown, BarChart3, Download, FlaskConical, Info, Play, Plus, SlidersHorizontal, Trash2 } from "lucide-react";
import { api, hostname, number, packageQuery, type EvaluationReport, type Package, type RetrievalExperiment, type RetrievalJob, type Run } from "./api";
import { Empty, ErrorMessage, ExternalLink, Spinner } from "./ui";
import { DensePanel, denseAvailable, JobProgress, useRetrieval } from "./Retrieval";
import { experiment, ExperimentFields, validExperiment } from "./ExperimentFields";
import { HitDiagnostics } from "./Search";
import { Select } from "./Select";
export { SearchPage } from "./Search";

type Draft = { key: number; config: RetrievalExperiment };
const jobLabel = (job: RetrievalJob) => `${job.created_at ? new Date(job.created_at).toLocaleString("ru-RU") : "Без даты"} · ${{ running: "выполняется", ready: "готово", failed: "ошибка", interrupted: "прервано" }[job.status]}${job.top_k ? ` · k = ${job.top_k}` : ""}`;

export function Evaluation({ run, pkg, onAnnotate }: { run: Run; pkg?: Package; onAnnotate: () => void }) {
  if (!pkg?.accepted) return <div className="panel"><Empty icon={<BarChart3 size={30} />} title="Сначала примите разметку" action={<button className="button primary" onClick={onAnnotate}>Перейти к разметке<ArrowRight size={16} /></button>}>Чтобы сравнивать конфигурации, оцените все пары и примите пакет. Разбиение dev/test сохранится автоматически.</Empty></div>;
  return <EvaluationWorkspace key={`${run.id}/${pkg.id}`} run={run} pkg={pkg} />;
}
function EvaluationWorkspace({ run, pkg }: { run: Run; pkg: Package }) {
  const retrieval = useRetrieval(run.id);
  const denseReady = denseAvailable(retrieval);
  const base = `/runs/${encodeURIComponent(run.id)}`;
  const suffix = packageQuery(pkg.id);
  const storageKey = `gather.evaluation.${run.id}/${pkg.id}`;
  const nextKey = useRef(2);
  const [drafts, setDrafts] = useState<Draft[]>([{ key: 0, config: experiment("Сбалансированная") }, { key: 1, config: { ...experiment("Приоритет заголовка"), sparse_config: { title_weight: 3, text_weight: 1 } } }]);
  const [topK, setTopK] = useState(5);
  const [history, setHistory] = useState<RetrievalJob[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState("");
  const [historyRevision, setHistoryRevision] = useState(0);
  const [selectedId, setSelectedId] = useState("");
  const [job, setJob] = useState<RetrievalJob | null>(null);
  const [report, setReport] = useState<EvaluationReport | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [detailRevision, setDetailRevision] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const postController = useRef<AbortController | null>(null);
  const restoredReport = useRef("");
  useEffect(() => () => postController.current?.abort(), []);

  useEffect(() => {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function read() {
      try {
        const result = await api<{ evaluations: RetrievalJob[]; active_job: RetrievalJob | null }>(`${base}/evaluations${suffix}`, { signal: abort.signal });
        if (abort.signal.aborted) return;
        setHistory(result.evaluations);
        setHistoryError(""); setHistoryLoading(false);
        setSelectedId(current => {
          if (current) return current;
          let saved = "";
          try { saved = localStorage.getItem(storageKey) || ""; } catch { /* Browser storage is optional. */ }
          return result.evaluations.some(item => item.id === saved) ? saved : result.evaluations.find(item => item.status === "running")?.id || result.evaluations[0]?.id || "";
        });
        timer = setTimeout(() => void read(), result.active_job ? 1500 : 5000);
      } catch (e) {
        if (abort.signal.aborted) return;
        setHistoryLoading(false); setHistoryError((e as Error).message);
        timer = setTimeout(() => void read(), 5000);
      }
    }
    void read();
    return () => { abort.abort(); clearTimeout(timer); };
  }, [base, suffix, storageKey, historyRevision]);

  useEffect(() => {
    setReport(null); setJob(null); setDetailError("");
    if (!selectedId) return;
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setDetailLoading(true);
    try { localStorage.setItem(storageKey, selectedId); } catch { /* Browser storage is optional. */ }
    async function read() {
      try {
        const result = await api<{ job: RetrievalJob; report: EvaluationReport | null }>(`${base}/evaluations/${encodeURIComponent(selectedId)}${suffix}`, { signal: abort.signal });
        if (abort.signal.aborted) return;
        setJob(result.job); setDetailLoading(false); setDetailError("");
        setHistory(items => items.map(item => item.id === result.job.id ? result.job : item));
        if (result.report) {
          setReport(result.report);
          if (restoredReport.current !== result.report.id) {
            restoredReport.current = result.report.id;
            setTopK(result.report.top_k);
            setDrafts(result.report.reports.map(item => ({ key: nextKey.current++, config: { ...experiment(item.name), ...item.config, name: item.name } })));
          }
        }
        if (result.job.status === "running") timer = setTimeout(() => void read(), 1000);
      } catch (e) {
        if (abort.signal.aborted) return;
        setDetailError((e as Error).message); setDetailLoading(false);
        timer = setTimeout(() => void read(), 5000);
      }
    }
    void read();
    return () => { abort.abort(); clearTimeout(timer); };
  }, [selectedId, base, suffix, storageKey, detailRevision]);

  const active = submitting || job?.status === "running" || history.some(item => item.status === "running") || retrieval.state?.active_job?.status === "running";
  const names = drafts.map(item => item.config.name.trim());
  const uniqueNames = new Set(names).size === names.length;
  const needsDense = drafts.some(item => item.config.mode !== "bm25");
  const valid = drafts.length > 0 && uniqueNames && drafts.every(item => validExperiment(item.config)) && (!needsDense || denseReady) && Number.isInteger(topK) && topK > 0 && topK <= 100;
  async function evaluate(event: FormEvent) {
    event.preventDefault();
    if (!valid || active || !run.components?.index) return;
    const abort = new AbortController(); postController.current = abort;
    setSubmitting(true); setSubmitError("");
    try {
      const result = await api<RetrievalJob>(`${base}/evaluate${suffix}`, { method: "POST", signal: abort.signal, body: JSON.stringify({ top_k: topK, experiments: drafts.map(item => ({ ...item.config, name: item.config.name.trim() })) }) });
      if (abort.signal.aborted) return;
      setJob(result); setReport(null); setSelectedId(result.id);
      setHistory(items => [result, ...items.filter(item => item.id !== result.id)]);
      setHistoryRevision(value => value + 1);
      retrieval.refresh();
    } catch (e) { if (!abort.signal.aborted) setSubmitError((e as Error).message); }
    finally { if (!abort.signal.aborted) setSubmitting(false); }
  }
  const labelSource = report?.label_source ?? pkg.label_source;
  return <>
    <section className="evaluation-setup panel">
      <div className="eval-heading"><span className="summary-icon"><FlaskConical size={23} strokeWidth={1.5} /></span><h2>Сравнение настроек поиска</h2></div>
      <form onSubmit={evaluate}>
        <div className="evaluation-toolbar"><label className="retrieval-label">Глубина выдачи и метрик (k)<input type="number" required min={1} max={100} value={topK} disabled={active || historyLoading || detailLoading} onChange={e => setTopK(Number(e.target.value))} /></label></div>
        {drafts.map((item, index) => <fieldset key={item.key} className="experiment-editor" disabled={active || historyLoading || detailLoading}><legend>Эксперимент {index + 1}</legend>
          <div className="experiment-topline"><label className="retrieval-label">Название эксперимента<input required maxLength={100} value={item.config.name} onChange={e => setDrafts(items => items.map(draft => draft.key === item.key ? { ...draft, config: { ...draft.config, name: e.target.value } } : draft))} /></label>
            <button type="button" className="button" aria-label="Удалить эксперимент" disabled={drafts.length <= 1} onClick={() => setDrafts(items => items.filter(draft => draft.key !== item.key))}><Trash2 size={14} />Удалить</button></div>
          <ExperimentFields value={item.config} onChange={value => setDrafts(items => items.map(draft => draft.key === item.key ? { ...draft, config: value } : draft))} denseReady={denseReady} disabled={active || historyLoading || detailLoading} />
        </fieldset>)}

        {!uniqueNames && <p className="notice" role="alert">Названия экспериментов должны быть уникальными.</p>}
        {needsDense && !denseReady && <p className="notice">Для этих экспериментов нужен готовый dense и доступный Qdrant. Подготовьте dense или выберите BM25.</p>}
        {!run.components?.index && <p className="notice">Нужен поисковый индекс. Сохранённые отчёты можно просматривать.</p>}
        <div className="eval-actions"><button type="button" className="button" disabled={active || historyLoading || detailLoading || drafts.length >= 20} onClick={() => { const key = nextKey.current++; setDrafts(items => [...items, { key, config: experiment(`Эксперимент ${key + 1}`) }]); }}><Plus size={14} />Добавить эксперимент</button><button className="button primary" disabled={active || historyLoading || detailLoading || !valid || !run.components?.index}>{active ? <Spinner /> : <Play size={15} />}{active ? "Операция выполняется…" : "Запустить сравнение"}</button></div>
      </form>
      {submitError && <ErrorMessage message={submitError} />}

    </section>
    <section className="panel evaluation-history"><h3>Сохранённые сравнения</h3>
      {historyLoading && <div className="loading-state"><Spinner />Загружаем историю…</div>}
      {historyError && <ErrorMessage message={historyError} retry={() => setHistoryRevision(v => v + 1)} />}
      {history.length > 0 ? <div className="retrieval-label"><span>Отчёт сравнения</span><Select label="Отчёт сравнения" variant="field" value={selectedId} onChange={id => { restoredReport.current = ""; setSelectedId(id); }} options={[{ value: "", label: "Выберите отчёт", disabled: true }, ...history.map(item => ({ value: item.id, label: jobLabel(item) }))]} /></div> : !historyLoading && !historyError && <p className="muted">Сохранённых сравнений пока нет.</p>}
      {detailLoading && <div className="loading-state"><Spinner />Загружаем сравнение…</div>}
      {detailError && <ErrorMessage message={detailError} retry={() => setDetailRevision(v => v + 1)} />}
      {job && job.status !== "ready" && <JobProgress job={job} />}
      {job?.status === "ready" && !report && !detailError && <p className="notice">Операция завершена, но отчёт недоступен.</p>}
    </section>
    {labelSource === "assistant_smoke" && <div className="notice"><Info size={16} />Тестовая разметка ассистента. Эти метрики не подходят для выводов о качестве поиска.</div>}
    {report ? <SavedComparison key={report.id} report={report} runId={run.id} /> : !active && !detailLoading && !detailError && <Empty icon={<SlidersHorizontal size={28} />} title="Сравнение ещё не запущено">Настройте эксперименты и запустите сравнение или откройте сохранённый отчёт.</Empty>}

    <DensePanel run={run} resource={retrieval} />
  </>;
}

function SavedComparison({ report, runId }: { report: EvaluationReport; runId: string }) {
  const [exporting, setExporting] = useState<string | null>(null);
  const [exportError, setExportError] = useState("");
  async function downloadProject(name: string) {
    setExporting(name); setExportError("");
    try {
      const params = new URLSearchParams({ package: report.package, experiment: name });
      const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/evaluations/${encodeURIComponent(report.id)}/export?${params}`);
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(typeof body?.detail === "string" ? body.detail : `Не удалось экспортировать проект (${response.status}).`);
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url; link.download = `${runId}-search.zip`;
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setExportError((e as Error).message); }
    finally { setExporting(null); }
  }
  const [sort, setSort] = useState<{ key: string; direction: "ascending" | "descending" } | null>(null);
  const metrics = [{ key: `nDCG@${report.top_k}`, label: "nDCG" }, { key: `P(rel=2)@${report.top_k}`, label: "Precision" }, { key: `R(rel=2)@${report.top_k}`, label: "Recall" }, { key: `Judged@${report.top_k}`, label: "Judged" }];
  const columns = [...metrics.map(metric => ({ ...metric, label: `${metric.label}@${report.top_k}` })), { key: "search_seconds", label: "Поиск, s" }];
  const value = (entry: EvaluationReport["reports"][number], key: string) => {
    const result = key === "search_seconds" ? entry.timing?.search_seconds : entry.evaluation.aggregate[key];
    return typeof result === "number" ? result : undefined;
  };
  const rows = sort ? [...report.reports].sort((a, b) => {
    const left = value(a, sort.key), right = value(b, sort.key);
    if (left == null) return right == null ? 0 : 1;
    if (right == null) return -1;
    return (left - right) * (sort.direction === "ascending" ? 1 : -1);
  }) : report.reports;
  function toggleSort(key: string) {
    setSort(current => current?.key !== key ? { key, direction: "ascending" } : current.direction === "ascending" ? { key, direction: "descending" } : null);
  }
  return <>
    <div className="section-heading"><h2>Результаты сравнения</h2><span className="weak-badge">DEV · @{report.top_k}</span></div>
    <div className="evaluation-report-summary"><span>Полный корпус: {number(report.corpus_documents)} документов</span><span>Запросов dev: {Object.keys(report.queries).length}</span></div>
    <div className="metrics-grid">{metrics.map(metric => <div className="metric-card panel" key={metric.key}><span className="metric-name">{metric.label}<small>@{report.top_k}</small></span>{report.reports.map(entry => <div className="metric-value-row" key={entry.name}><span className="metric-config-name">{entry.name}</span><strong className="mono">{entry.evaluation.aggregate[metric.key]?.toFixed(3) ?? "—"}</strong><div className="metric-track"><span style={{ width: `${Math.max(0, Math.min(1, entry.evaluation.aggregate[metric.key] || 0)) * 100}%` }} /></div></div>)}</div>)}</div>
    <section className="panel comparison-panel"><div className="table-scroll"><table><thead><tr><th>Конфигурация</th>{columns.map(column => {
      const direction = sort?.key === column.key ? sort.direction : "none";
      const Icon = direction === "ascending" ? ArrowUp : direction === "descending" ? ArrowDown : ArrowUpDown;
      return <th key={column.key} scope="col" aria-sort={direction}><button type="button" className="metric-sort" onClick={() => toggleSort(column.key)}>{column.label}<Icon size={13} aria-hidden="true" /></button></th>;
    })}</tr></thead><tbody>{rows.map(entry => <tr key={entry.name}><td>{entry.name}<small className="mono">{entry.config.mode.toUpperCase()}</small></td>{metrics.map(metric => <td className="mono" key={metric.key}>{entry.evaluation.aggregate[metric.key]?.toFixed(3) ?? "—"}</td>)}<td className="mono">{typeof entry.timing?.search_seconds === "number" ? entry.timing.search_seconds.toFixed(4) : "—"}</td></tr>)}</tbody></table></div></section>
    <section className="panel export-panel"><h3>Экспорт поискового сервиса</h3>
      <p className="muted">ZIP с исходниками API, полным корпусом и настройками выбранного BM25-эксперимента. Индекс строится при развёртывании; Gather и LLM-ключи не нужны.</p>
      <div className="eval-actions">{report.reports.map(entry => <button type="button" className="button" key={entry.name} disabled={exporting !== null || entry.config.mode !== "bm25"} title={entry.config.mode !== "bm25" ? "Экспорт Dense/Hybrid пока не поддерживается" : undefined} onClick={() => void downloadProject(entry.name)}>{exporting === entry.name ? <Spinner /> : <Download size={15} />}<span>{exporting === entry.name ? "Собираем архив…" : `Экспорт: ${entry.name}`}</span></button>)}</div>
      {exportError && <ErrorMessage message={exportError} />}
    </section>
    <details className="evaluation-help"><summary>О метриках и времени</summary><p>Для Precision и Recall релевантны оценки 2–3. Recall учитывает только размеченные документы; Judged показывает покрытие оценками.</p><p>Время учитывает кэш каналов между экспериментами, без загрузки модели и индекса.</p></details>
    <section className="panel per-query"><h3>По запросам</h3>{Object.entries(report.queries).map(([qid, query]) => <div className="query-comparison" key={qid}><h3>{query}</h3><div className="ranked-comparisons">{report.reports.map(entry => <section className="ranked-comparison" key={entry.name}><h3>{entry.name}</h3><p className="mono">nDCG@{report.top_k}: {entry.evaluation.per_query[qid]?.[`nDCG@${report.top_k}`]?.toFixed(3) ?? "—"}</p>{entry.results?.[qid]?.length ? <ol>{entry.results[qid].map((hit, i) => {
      const grade = report.qrels[qid]?.[hit.url];
      return <li key={`${hit.url}/${i}`}><ExternalLink url={hit.url}>{hit.title || hit.url}</ExternalLink><p className="mono">{hostname(hit.url)} · score {hit.score.toFixed(3)}</p><span className="grade-label">{grade == null ? "не размечен" : `Оценка: ${grade}`}</span><p>{hit.text || "Предпросмотр текста недоступен."}</p>{entry.config.mode === "hybrid" && <details><summary>Ранги каналов</summary><HitDiagnostics hit={hit} /></details>}</li>;
    })}</ol> : <p className="muted">Результатов нет.</p>}</section>)}</div></div>)}</section>
  </>;
}
