import { useRef, useState, type FormEvent } from "react";
import {
  ArrowRight,
  BarChart3,
  Check,
  ChevronDown,
  FileSearch,
  FlaskConical,
  Info,
  Play,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import {
  api,
  hostname,
  number,
  packageQuery,
  type Hit,
  type Package,
  type Report,
  type Run,
} from "./api";
import { Empty, ErrorMessage, ExternalLink, Spinner } from "./ui";

export function SearchPage({ run }: { run: Run }) {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [expanded, setExpanded] = useState<string | null>(null);
  const generation = useRef(0);
  async function search(event: FormEvent) {
    event.preventDefault();
    if (!input.trim()) return;
    const id = ++generation.current;
    const started = performance.now();
    const text = input.trim();
    setBusy(true);
    setError("");
    setExpanded(null);
    try {
      const result = await api<{ hits: Hit[] }>(
        `/runs/${encodeURIComponent(run.id)}/search?q=${encodeURIComponent(text)}`,
      );
      if (generation.current === id) {
        setHits(result.hits);
        setQuery(text);
        setElapsed(Math.round(performance.now() - started));
      }
    } catch (e) {
      if (generation.current === id) {
        setError((e as Error).message);
        setHits([]);
        setQuery("");
      }
    } finally {
      if (generation.current === id) setBusy(false);
    }
  }
  return (
    <>
      <section className="search-surface panel">
        <div className="search-intro">
          <span className="search-symbol">
            <FileSearch size={30} strokeWidth={1.3} />
          </span>
          <div>
            <h2>Ваш корпус. Ваши вопросы.</h2>
            <p>Поиск BM25 по заголовкам и содержимому документов.</p>
          </div>
          <span className="engine-tag mono">TANTIVY / BM25</span>
        </div>
        <form onSubmit={search} className="search-form">
          <Search size={20} />
          <input
            autoFocus
            aria-label="Поисковый запрос"
            value={input}
            maxLength={1000}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Что вы хотите найти?"
            required
          />
          <button className="button primary" disabled={busy || !input.trim()}>
            {busy ? <Spinner /> : <ArrowRight size={18} />}
            <span>{busy ? "Ищем…" : "Найти"}</span>
          </button>
        </form>
        <div className="search-meta">
          <span>
            <span className="local-dot" />
            {number(run.documents)} документов в индексе
          </span>
          <span>Обычный текст · до 10 результатов</span>
        </div>
      </section>
      {error && <ErrorMessage message={error} />}
      {busy && (
        <div className="loading-state">
          <Spinner />
          Ищем в корпусе…
        </div>
      )}
      {!busy && !query && !error && (
        <Empty icon={<Search size={26} />} title="Начните с вопроса">
          Название API, термин или задача — запрос останется обычным текстом,
          даже если в нём есть специальные символы.
        </Empty>
      )}
      {!busy && query && (
        <>
          <div className="section-heading result-heading">
            <h2>
              {hits.length ? `Результаты для «${query}»` : "Ничего не найдено"}
            </h2>
            <span className="mono muted">
              {hits.length} результатов · {elapsed} ms
            </span>
          </div>
          {!hits.length ? (
            <div className="panel">
              <Empty
                icon={<FileSearch size={26} />}
                title="Попробуйте другую формулировку"
              >
                Уточните термин или сократите запрос. Поиск работает только по
                собранному корпусу.
              </Empty>
            </div>
          ) : (
            <div className="search-results">
              {hits.map((hit, i) => (
                <article className="search-result panel" key={hit.url}>
                  <span className="result-rank mono">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <div className="result-content">
                    <ExternalLink url={hit.url}>
                      {hostname(hit.url)}
                    </ExternalLink>
                    <h3>
                      <ExternalLink url={hit.url}>{hit.title}</ExternalLink>
                    </h3>
                    <p
                      className={
                        expanded === hit.url
                          ? "result-excerpt expanded"
                          : "result-excerpt"
                      }
                    >
                      {hit.text || "Предпросмотр текста недоступен."}
                    </p>
                    <button
                      className="text-button"
                      onClick={() =>
                        setExpanded(expanded === hit.url ? null : hit.url)
                      }
                    >
                      {expanded === hit.url ? "Свернуть" : "Читать фрагмент"}
                      <ChevronDown
                        size={13}
                        className={expanded === hit.url ? "rotate" : ""}
                      />
                    </button>
                  </div>
                  <span className="score mono">
                    {hit.score.toFixed(2)}
                    <small>score</small>
                  </span>
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </>
  );
}

const metrics = [
  { key: "nDCG@5", label: "nDCG", note: "Порядок и релевантность" },
  { key: "P(rel=2)@5", label: "Precision", note: "Доля полезных результатов" },
  { key: "R(rel=2)@5", label: "Recall", note: "Полнота по разметке" },
  { key: "Judged@5", label: "Judged", note: "Покрытие оценками" },
];
export function Evaluation({
  run,
  pkg,
  onAnnotate,
}: {
  run: Run;
  pkg?: Package;
  onAnnotate: () => void;
}) {
  const [reports, setReports] = useState<Report[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [labelSource, setLabelSource] = useState(pkg?.label_source);
  async function evaluate() {
    if (!pkg) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<{
        reports: Report[];
        split: string;
        label_source: string | null;
      }>(
        `/runs/${encodeURIComponent(run.id)}/evaluate${packageQuery(pkg.id)}`,
        { method: "POST" },
      );
      setReports(result.reports);
      setLabelSource(result.label_source);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!pkg?.accepted)
    return (
      <div className="panel">
        <Empty
          icon={<BarChart3 size={30} />}
          title="Сначала — эталонная разметка"
          action={
            <button className="button primary" onClick={onAnnotate}>
              Перейти к разметке
              <ArrowRight size={16} />
            </button>
          }
        >
          Чтобы сравнивать конфигурации, оцените все пары и примите пакет.
          Разбиение dev/test сохранится автоматически.
        </Empty>
      </div>
    );
  return (
    <>
      <section className="evaluation-setup panel">
        <div className="eval-heading">
          <span className="summary-icon">
            <FlaskConical size={23} strokeWidth={1.5} />
          </span>
          <div>
            <span className="eyebrow">КОНТРОЛИРУЕМЫЙ ЭКСПЕРИМЕНТ</span>
            <h2>Одинаковые данные. Разные настройки.</h2>
            <p>Две конфигурации BM25 на одном индексе и dev-наборе.</p>
          </div>
        </div>
        <div className="experiment-configs">
          <div>
            <span className="config-dot" />
            <strong>Сбалансированная</strong>
            <span className="mono">title 1.0 / text 1.0</span>
          </div>
          <div>
            <span className="config-dot secondary" />
            <strong>Приоритет заголовка</strong>
            <span className="mono">title 3.0 / text 1.0</span>
          </div>
        </div>
        <div className="eval-actions">
          <span>
            <Check size={15} />
            Разметка зафиксирована<span className="split-badge">DEV · @5</span>
          </span>
          <button
            className="button primary"
            disabled={busy}
            onClick={() => void evaluate()}
          >
            {busy ? <Spinner /> : <Play size={15} />}
            {busy
              ? "Считаем метрики…"
              : reports.length
                ? "Пересчитать"
                : "Запустить сравнение"}
          </button>
        </div>
      </section>
      {error && <ErrorMessage message={error} retry={() => void evaluate()} />}
      {labelSource === "assistant_smoke" && (
        <div className="notice">
          <Info size={16} />
          Приблизительная разметка ассистента. Значения подтверждают работу
          пайплайна, а не качество поиска.
        </div>
      )}
      {reports.length > 0 ? (
        <>
          <div className="section-heading">
            <div>
              <h2>Результаты сравнения</h2>
              <p>Агрегированные метрики по запросам dev-набора.</p>
            </div>
            <span className="weak-badge">TEST НЕ ИСПОЛЬЗУЕТСЯ</span>
          </div>
          <div className="metrics-grid">
            {metrics.map((metric) => (
              <div className="metric-card panel" key={metric.key}>
                <span className="metric-name">
                  {metric.label}
                  <small>@5</small>
                </span>
                <p>{metric.note}</p>
                {reports.map((report, i) => (
                  <div className="metric-value-row" key={report.name}>
                    <span className={`config-dot ${i ? "secondary" : ""}`} />
                    <span className="mono">
                      {report.evaluation.aggregate[metric.key]?.toFixed(3) ??
                        "—"}
                    </span>
                    <div className="metric-track">
                      <span
                        style={{
                          width: `${Math.max(0, Math.min(1, report.evaluation.aggregate[metric.key] || 0)) * 100}%`,
                          opacity: i ? 0.45 : 1,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
          <section className="panel comparison-panel">
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Конфигурация</th>
                    {metrics.map((metric) => (
                      <th key={metric.key}>{metric.label}@5</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {reports.map((report, i) => (
                    <tr key={report.name}>
                      <td>
                        <span
                          className={`config-dot ${i ? "secondary" : ""}`}
                        />
                        {report.name === "equal"
                          ? "Сбалансированная"
                          : report.name === "title-boost"
                            ? "Приоритет заголовка"
                            : report.name}
                        <small className="mono">
                          {report.config.title_weight} /{" "}
                          {report.config.text_weight}
                        </small>
                      </td>
                      {metrics.map((metric) => (
                        <td className="mono" key={metric.key}>
                          {report.evaluation.aggregate[metric.key]?.toFixed(
                            3,
                          ) ?? "—"}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="panel per-query">
            <h3>По запросам</h3>
            {Object.keys(reports[0].evaluation.per_query).map((qid) => (
              <div className="query-metrics" key={qid}>
                <span className="mono">{qid.toUpperCase()}</span>
                {reports.map((report) => (
                  <span key={report.name}>
                    {report.name}
                    <strong className="mono">
                      nDCG{" "}
                      {report.evaluation.per_query[qid]?.["nDCG@5"]?.toFixed(
                        3,
                      ) ?? "—"}
                    </strong>
                  </span>
                ))}
              </div>
            ))}
          </section>
        </>
      ) : (
        !busy && (
          <Empty
            icon={<SlidersHorizontal size={28} />}
            title="Не угадывайте — сравнивайте"
          >
            Запустите эксперимент, чтобы увидеть реальные метрики поиска по
            принятой разметке. Без вызовов LLM.
          </Empty>
        )
      )}
      <div className="evaluation-footnote">
        <Info size={16} />
        <p>
          Для Precision и Recall релевантны оценки 2–3. Recall учитывает только
          размеченные документы; низкий Judged означает неполную оценку выдачи.
          Test-набор не участвует в подборе настроек.
        </p>
      </div>
    </>
  );
}
