import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, packageQuery, type ActiveConfig, type Package, type RetrievalJob, type RetrievalReport, type Run } from "./api";
import { JobProgress, type RetrievalResource } from "./Retrieval";
import { Select } from "./Select";
import { ErrorMessage, Spinner } from "./ui";

type Settings = { top_k: number; max_experiments: number; max_model_calls: number; patience: number; min_improvement: number; min_judged: number; auto_apply: boolean };
type OptimizerReport = {
  status: string; stop_reason: string | null; settings: Omit<Settings, "auto_apply">; objective: string;
  experiments: (RetrievalReport & { eligible: boolean })[];
  decisions: { decision: { action: string; reason: string }; observation: unknown }[];
  best_name: string | null; baseline_best_name: string | null; agent_improved: boolean; model_calls: number; label_source?: string;
};
type Detail = { job: RetrievalJob; report: OptimizerReport | null; active_config: ActiveConfig | null };
const defaults: Settings = { top_k: 5, max_experiments: 12, max_model_calls: 8, patience: 3, min_improvement: 0.001, min_judged: 0.8, auto_apply: true };
const fields = [
  { key: "top_k", label: "Глубина метрик (k)", min: 1, max: 100, step: 1 },
  { key: "max_experiments", label: "Максимум экспериментов", min: 3, max: 100, step: 1 },
  { key: "max_model_calls", label: "Максимум вызовов модели", min: 1, max: 100, step: 1 },
  { key: "patience", label: "Терпение (пакетов без улучшения)", min: 1, step: 1 },
  { key: "min_improvement", label: "Минимальное улучшение", min: 0, step: "any" },
  { key: "min_judged", label: "Минимум Judged", min: 0, max: 1, step: "any" },
] as const;

export function OptimizationPanel({ run, pkg, resource }: { run: Run; pkg: Package; resource: RetrievalResource }) {
  const base = `/runs/${encodeURIComponent(run.id)}`;
  const suffix = packageQuery(pkg.id);
  const [settings, setSettings] = useState(defaults);
  const [history, setHistory] = useState<RetrievalJob[]>([]);
  const [activeJob, setActiveJob] = useState<RetrievalJob | null>(null);
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(true);
  const [historyError, setHistoryError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [pending, setPending] = useState(false);
  const [revision, setRevision] = useState(0);
  const post = useRef<AbortController | null>(null);
  const refreshRetrieval = useRef(resource.refresh);
  refreshRetrieval.current = resource.refresh;
  useEffect(() => () => post.current?.abort(), []);

  useEffect(() => {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function read() {
      try {
        const result = await api<{ optimizations: RetrievalJob[]; active_job: RetrievalJob | null }>(`${base}/optimizations${suffix}`, { signal: abort.signal });
        if (abort.signal.aborted) return;
        setHistory(result.optimizations); setActiveJob(result.active_job); setHistoryError(""); setLoading(false);
        setSelected(id => id || result.optimizations.find(item => item.status === "running")?.id || result.optimizations[0]?.id || "");
        timer = setTimeout(() => void read(), result.active_job?.status === "running" ? 1000 : 5000);
      } catch (e) {
        if (abort.signal.aborted) return;
        setLoading(false); setHistoryError((e as Error).message);
        timer = setTimeout(() => void read(), 5000);
      }
    }
    void read();
    return () => { abort.abort(); clearTimeout(timer); };
  }, [base, suffix, revision]);

  useEffect(() => {
    setDetail(null); setDetailError("");
    if (!selected) return;
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function read() {
      try {
        const result = await api<Detail>(`${base}/optimizations/${encodeURIComponent(selected)}${suffix}`, { signal: abort.signal });
        if (abort.signal.aborted) return;
        setDetail(result); setDetailError("");
        setHistory(items => items.map(item => item.id === result.job.id ? result.job : item));
        if (result.job.status === "running") timer = setTimeout(() => void read(), 1000);
        else refreshRetrieval.current();
      } catch (e) {
        if (abort.signal.aborted) return;
        setDetailError((e as Error).message);
        timer = setTimeout(() => void read(), 5000);
      }
    }
    void read();
    return () => { abort.abort(); clearTimeout(timer); };
  }, [base, suffix, selected, revision]);

  const job = detail?.job || history.find(item => item.id === selected);
  const report = detail?.report;
  const active = pending || job?.status === "running" || history.some(item => item.status === "running") || activeJob?.status === "running" || resource.state?.active_job?.status === "running";
  const valid = fields.every(field => Number.isFinite(settings[field.key]) && settings[field.key] >= field.min && (!("max" in field) || settings[field.key] <= field.max) && (field.step !== 1 || Number.isInteger(settings[field.key])));
  async function launch(event: FormEvent) {
    event.preventDefault();
    if (active || !valid || !run.components.index) return;
    const abort = new AbortController(); post.current = abort;
    setPending(true); setSubmitError("");
    try {
      const result = await api<RetrievalJob>(`${base}/optimize${suffix}`, { method: "POST", body: JSON.stringify(settings), signal: abort.signal });
      if (abort.signal.aborted) return;
      setHistory(items => [result, ...items.filter(item => item.id !== result.id)]);
      setSelected(result.id); setDetail(null); setRevision(value => value + 1);
      refreshRetrieval.current();
    } catch (e) { if (!abort.signal.aborted) setSubmitError((e as Error).message); }
    finally { if (!abort.signal.aborted) setPending(false); }
  }
  const applied = resource.state ? resource.state.active_config : detail?.active_config;
  return <section className="panel dense-panel optimization-panel" aria-label="Оптимизация BM25">
    <div className="section-heading"><h2>Оптимизация BM25</h2><button type="button" className="text-button" onClick={() => { setRevision(value => value + 1); refreshRetrieval.current(); }}>Обновить оптимизации</button></div>
    <p className="notice">Оптимизация вызывает настроенную LLM: провайдер может быть платным. Запросы, метрики и фрагменты корпуса могут передаваться провайдеру модели. Бюджет вызовов не является лимитом стоимости.</p>
    <p>Только принятый dev-пакет; test не используется. Подбираются веса полей BM25, dense не нужен. Три базовых эксперимента входят в бюджет.</p>
    <form onSubmit={launch}>
      <fieldset className="retrieval-fieldset" disabled={!!active}>
        <div className="retrieval-fields">{fields.map(field => <label key={field.key}>{field.label}<input type="number" required min={field.min} max={"max" in field ? field.max : undefined} step={field.step} value={settings[field.key]} onChange={event => setSettings(value => ({ ...value, [field.key]: Number(event.target.value) }))} /></label>)}
          <label className="checkbox-field"><input type="checkbox" checked={settings.auto_apply} onChange={event => setSettings(value => ({ ...value, auto_apply: event.target.checked }))} />Автоматически применять победителя</label>
        </div>
      </fieldset>
      <p>Применённый победитель становится серверной настройкой поиска; ручные настройки поиска действуют только в запросе.</p>
      <button className="button primary" disabled={!!active || !valid || loading || !!historyError || !run.components.index}>{active ? <Spinner /> : null}{active ? "Оптимизация / другая операция выполняется…" : "Запустить оптимизацию"}</button>
      {submitError && <ErrorMessage message={submitError} />}
    </form>
    <h3>История оптимизаций</h3>
    {loading && <p><Spinner /> Загружаем историю…</p>}
    {historyError && <ErrorMessage message={historyError} retry={() => setRevision(value => value + 1)} />}
    {!loading && !historyError && !history.length && <p>Сохранённых оптимизаций пока нет.</p>}
    {!!history.length && <Select label="Отчёт оптимизации" variant="field" value={selected} onChange={setSelected} options={history.map(item => ({ value: item.id, label: `${item.created_at ? new Date(item.created_at).toLocaleString("ru-RU") : item.id} · ${item.id} · ${item.status}` }))} />}
    {detailError && <ErrorMessage message={detailError} retry={() => setRevision(value => value + 1)} />}
    {job && <><JobProgress job={job} /><p className="mono">Вызовы модели: {job.model_calls ?? report?.model_calls ?? 0} / {job.max_model_calls ?? report?.settings.max_model_calls ?? "?"} · Экспериментов: {job.completed} / {job.total ?? "?"}</p></>}
    {job?.status === "ready" && applied?.job_id === job.id ? <p className="notice"><strong>Победитель применён к поиску</strong> · {applied.config.name} · Заголовок: {applied.config.sparse_config.title_weight} · Текст: {applied.config.sparse_config.text_weight} · {applied.applied_at}</p> : job && job.status !== "running" && <p className="notice">Эта оптимизация не является активной конфигурацией поиска.</p>}
    {report && <>
      {(job?.status === "failed" || job?.status === "interrupted") && <p className="notice">Сохранён промежуточный отчёт; результат не применён. Можно проверить эксперименты и решения, затем запустить новую оптимизацию.</p>}
      <div className="retrieval-status"><strong>Победитель: {report.best_name ?? "не выбран"}</strong><span>Базовый победитель: {report.baseline_best_name ?? "не выбран"}</span><span>{report.agent_improved ? "Агент улучшил базовый результат" : "Улучшение относительно базового результата не подтверждено"}</span></div>
      <p>Цель: {report.objective} · Статус отчёта: {report.status} · Причина остановки: {report.stop_reason ?? "—"}</p>
      {report.stop_reason === "insufficient_judgments" && <p className="notice" role="alert">Недостаточно оценок для выбора победителя: покрытие Judged ниже порога {report.settings.min_judged}. Дополните разметку. Неразмеченные документы не считаются доказанно нерелевантными; новая конфигурация не применяется.</p>}
      {report.label_source === "assistant_smoke" && <p className="notice">Тестовая разметка ассистента: не является доказательством качества поиска.</p>}
      <div className="table-scroll"><table><thead><tr><th>Эксперимент</th><th>Вес заголовка</th><th>Вес текста</th><th>{report.objective}</th><th>Judged@{report.settings.top_k}</th><th>Допущен</th></tr></thead><tbody>{report.experiments.map(entry => <tr key={entry.name}><td>{entry.name}</td><td>{entry.config.sparse_config.title_weight}</td><td>{entry.config.sparse_config.text_weight}</td><td>{entry.evaluation.aggregate[report.objective]?.toFixed(3) ?? "—"}</td><td>{entry.evaluation.aggregate[`Judged@${report.settings.top_k}`]?.toFixed(3) ?? "—"}</td><td>{entry.eligible ? "Да" : "Нет: недостаточно оценок"}</td></tr>)}</tbody></table></div>
      <h3>Решения агента</h3>
      {!report.decisions.length && <p>Решений пока нет.</p>}
      <ol className="optimization-decisions">{report.decisions.map((event, index) => <li key={index}><strong>{event.decision.action}</strong><p>{event.decision.reason}</p><details><summary>Наблюдение</summary><pre>{JSON.stringify(event.observation, null, 2)}</pre></details></li>)}</ol>
      <details><summary>Полный отчёт оптимизатора (JSON)</summary><pre>{JSON.stringify(report, null, 2)}</pre></details>
    </>}
    {job && !report && job.status !== "running" && !detailError && <p className="notice">Сохранённый отчёт недоступен. Подробности ошибки показаны выше.</p>}
  </section>;
}
