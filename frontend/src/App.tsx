import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  Check,
  Database,
  Files,
  Globe2,
  Layers2,
  ListFilter,
  Moon,
  Plus,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Sparkles,
  SquarePen,
} from "lucide-react";
import {
  api,
  hostname,
  number,
  sourceName,
  type Package,
  type Run,
  type View,
} from "./api";
import { Dialog, Empty, ErrorMessage, Spinner, Status } from "./ui";
import { Annotation } from "./Annotation";
import { Evaluation } from "./Explore";
import { SearchPage } from "./Search";
import { Sources } from "./Sources";
import { Documents } from "./Documents";
import { Select } from "./Select";

const navigation = [
  { id: "overview" as const, label: "Обзор", icon: Layers2 },
  { id: "sources" as const, label: "Источники", icon: Database },
  { id: "documents" as const, label: "Документы", icon: Files },
  { id: "annotation" as const, label: "Разметка", icon: SquarePen },
  { id: "search" as const, label: "Поиск", icon: Search },
  { id: "evaluation" as const, label: "Оценка", icon: SlidersHorizontal },
];
const stageNames = {
  analyze: "Анализ сайта",
  crawl: "Сбор документов",
  index: "Индексация",
  annotation: "Подготовка заданий",
  ready: "Готово",
};
function initialView(): View {
  const hash = window.location.hash.slice(1);
  return navigation.some((x) => x.id === hash) ? (hash as View) : "overview";
}

export default function App() {
  const [view, setView] = useState<View>(initialView);
  const [darkTheme, setDarkTheme] = useState(
    () => document.documentElement.dataset.theme === "dark",
  );
  useEffect(() => {
    const theme = darkTheme ? "dark" : "light";
    document.documentElement.dataset.theme = theme;
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute("content", darkTheme ? "#1c121b" : "#fcf8fa");
    try {
      localStorage.setItem("gather.theme", theme);
    } catch {
      // Theme switching still works if browser storage is unavailable.
    }
  }, [darkTheme]);
  const [allRuns, setRuns] = useState<Run[]>([]);
  const runs = allRuns.filter((run) => !run.archived);
  const [selected, setSelected] = useState(
    () => localStorage.getItem("gather.run") || "",
  );
  const [packageId, setPackageId] = useState("annotation");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [filter, setFilter] = useState("");
  const [toast, setToast] = useState("");
  const refresh = useCallback(async () => {
    try {
      const result = await api<{ runs: Run[] }>("/runs?include_archived=true");
      setRuns(result.runs);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), 4000);
    return () => clearInterval(id);
  }, [refresh]);
  useEffect(() => {
    const onHash = () => setView(initialView());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(""), 3200);
    return () => clearTimeout(id);
  }, [toast]);
  const run = runs.find((r) => r.id === selected) || runs[0];
  const pkg = run?.packages.find((p) => p.id === packageId) || run?.packages[0];
  function selectRun(id: string) {
    setSelected(id);
    localStorage.setItem("gather.run", id);
    setPackageId("annotation");
  }
  function navigate(next: View) {
    setView(next);
    window.location.hash = next;
  }
  const documents = runs.reduce((sum, r) => sum + r.documents, 0);
  const pairs = runs.reduce((sum, r) => sum + r.pairs, 0);
  const labeled = runs.reduce((sum, r) => sum + r.labeled, 0);

  return (
    <div className="app-shell">
      <header className="workspace-header">
        <div className="topbar">
          <a href="#overview" className="brand" aria-label="Gather — обзор">
            <span className="brand-mark" aria-hidden="true">
              &gt;_
            </span>
            <span>
              gather<span className="brand-period">.</span>
            </span>
            <span className="version">v0.1</span>
          </a>
          <div className="topbar-right">
            <button
              type="button"
              className="theme-toggle"
              role="switch"
              aria-label="Тёмная тема"
              aria-checked={darkTheme}
              title={
                darkTheme ? "Включить светлую тему" : "Включить тёмную тему"
              }
              onClick={() => setDarkTheme((current) => !current)}
            >
              <Moon size={16} aria-hidden="true" />
              <span className="theme-label">Тёмная тема</span>
              <span className="theme-track" aria-hidden="true" />
            </button>
          </div>
        </div>
        <nav className="workspace-nav" aria-label="Основная навигация">
          {navigation.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={`nav-item ${view === id ? "active" : ""}`}
              aria-label={label}
              data-view={id}
              aria-current={view === id ? "page" : undefined}
              title={label}
              onClick={() => navigate(id)}
            >
              <Icon size={18} strokeWidth={1.7} />
              <span>{label}</span>
              {id === "annotation" && pairs > labeled && (
                <span className="nav-count">{number(pairs - labeled)}</span>
              )}
            </button>
          ))}
        </nav>
      </header>

      <div className="main-shell">
        <main className={`workspace-${view}`}>
          {error && (
            <ErrorMessage message={error} retry={() => void refresh()} />
          )}
          <div className="page-heading">
            <div>
              <h1 aria-label={navigation.find((n) => n.id === view)?.label}>
                {navigation.find((n) => n.id === view)?.label}
              </h1>
            </div>
            {(view === "overview" || view === "sources") && (
              <button
                className="button primary"
                onClick={() => setCreating(true)}
              >
                <Plus size={17} />
                Новый запуск
              </button>
            )}
          </div>
          {loading ? (
            <div className="loading-state">
              <Spinner />
              Загрузка…
            </div>
          ) : (
            <>
              {view === "overview" ? (
                <>
                  <section
                    className="stats-grid"
                    aria-label="Статистика пространства"
                  >
                    <Stat
                      icon={<Globe2 size={18} />}
                      label="Источников"
                      to="sources"
                      value={number(runs.length)}
                    />
                    <Stat
                      icon={<Files size={18} />}
                      label="Документов"
                      to="documents"
                      value={number(documents)}
                    />
                    <Stat
                      icon={<SquarePen size={18} />}
                      label="Размечено пар"
                      to="annotation"
                      value={number(labeled)}
                      suffix={`/ ${number(pairs)}`}
                    />
                  </section>
                  <div className="section-heading">
                    <div>
                      <h2>
                        Источники{" "}
                        <span className="count-badge">{runs.length}</span>
                      </h2>
                    </div>
                    <div className="section-tools">
                      <div className="compact-search">
                        <Search size={15} />
                        <input
                          aria-label="Найти источник"
                          placeholder="Найти источник…"
                          value={filter}
                          onChange={(e) => setFilter(e.target.value)}
                        />
                      </div>
                      <button
                        className="icon-button"
                        aria-label="Обновить источники"
                        onClick={() => void refresh()}
                      >
                        <RefreshCw size={16} />
                      </button>
                    </div>
                  </div>
                  {!runs.length ? (
                    <div className="panel">
                      <Empty
                        icon={<Globe2 size={28} />}
                        title="Пока нет источников"
                        action={
                          <button
                            className="button primary"
                            onClick={() => setCreating(true)}
                          >
                            <Plus size={16} />
                            Добавить источник
                          </button>
                        }
                      >
                        Укажите адрес сайта и какие документы нужно собрать.
                      </Empty>
                    </div>
                  ) : (
                    <div className="sources-layout">
                      <div className="source-list">
                        {runs
                          .filter((r) =>
                            `${r.name} ${r.url} ${r.goal}`
                              .toLowerCase()
                              .includes(filter.toLowerCase()),
                          )
                          .map((r) => (
                            <button
                              key={r.id}
                              className={`source-card ${run?.id === r.id ? "selected" : ""}`}
                              onClick={() => selectRun(r.id)}
                            >
                              <div className="source-top">
                                <div className="source-title">
                                  <Globe2 size={16} strokeWidth={1.5} />
                                  <h3>{sourceName(r)}</h3>
                                </div>
                                <Status run={r} />
                              </div>
                              <div className="source-id mono">{r.id}</div>
                              <p>
                                {r.goal || "Сбор по сохранённому плану обхода."}
                              </p>
                              <div className="source-bottom">
                                <span>
                                  <Files size={14} />
                                  {number(r.documents)} документов
                                </span>
                                <ArrowUpRight size={16} />
                              </div>
                            </button>
                          ))}
                        {filter &&
                          !runs.some((r) =>
                            `${r.name} ${r.url} ${r.goal}`
                              .toLowerCase()
                              .includes(filter.toLowerCase()),
                          ) && (
                            <div className="small-empty">
                              Источники не найдены
                            </div>
                          )}
                      </div>
                      {run && (
                        <RunDetail run={run} pkg={pkg} navigate={navigate} />
                      )}
                    </div>
                  )}
                </>
              ) : view === "sources" ? (
                <Sources
                  runs={allRuns}
                  refresh={refresh}
                  notify={setToast}
                  onOpen={(id, next) => {
                    selectRun(id);
                    navigate(next);
                  }}
                />
              ) : !run ? (
                <div className="panel">
                  <Empty
                    icon={<Database size={28} />}
                    title="Пока нет источников"
                    action={
                      <button
                        className="button"
                        onClick={() => navigate("overview")}
                      >
                        К обзору
                        <ArrowRight size={16} />
                      </button>
                    }
                  >
                    Сначала создайте запуск в разделе «Обзор».
                  </Empty>
                </div>
              ) : (
                <>
                  <div className="context-bar">
                    <Select
                      label="Выбрать источник"
                      value={run.id}
                      onChange={selectRun}
                      icon={<Globe2 size={16} />}
                      options={runs.map((r) => ({
                        value: r.id,
                        label: `${sourceName(r)} · ${r.id}`,
                      }))}
                    />
                    {(view === "annotation" || view === "evaluation") &&
                      run.packages.length > 0 && (
                        <Select
                          key={run.id}
                          label="Выбрать пакет"
                          value={pkg?.id || ""}
                          onChange={setPackageId}
                          icon={<Layers2 size={15} />}
                          options={run.packages.map((p) => ({
                            value: p.id,
                            label: `${p.id}${p.label_source === "assistant_smoke" ? " · smoke" : ""}`,
                          }))}
                        />
                      )}
                    <span className="context-meta">
                      {number(run.documents)} документов
                    </span>
                  </div>
                  {view === "annotation" && (
                    <Annotation
                      key={`${run.id}/${pkg?.id}`}
                      run={run}
                      pkg={pkg}
                      refresh={refresh}
                      notify={setToast}
                      onEvaluate={() => navigate("evaluation")}
                    />
                  )}
                  {view === "search" && <SearchPage key={run.id} run={run} />}
                  {view === "documents" && <Documents key={run.id} run={run} />}
                  {view === "evaluation" && (
                    <Evaluation
                      key={`${run.id}/${pkg?.id}`}
                      run={run}
                      pkg={pkg}
                      onAnnotate={() => navigate("annotation")}
                    />
                  )}
                </>
              )}
            </>
          )}
        </main>
        <footer>
          <span>Gather / MAS Crawler</span>
        </footer>
      </div>
      {creating && (
        <NewRun
          onClose={() => setCreating(false)}
          onCreated={async (r) => {
            selectRun(r.id);
            setCreating(false);
            navigate("overview");
            await refresh();
            setToast("Сбор запущен.");
          }}
        />
      )}
      {toast && (
        <div className="toast" role="status">
          <Check size={17} />
          {toast}
        </div>
      )}
    </div>
  );
}

function Stat({
  icon,
  label,
  value,
  suffix,
  to,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  suffix?: string;
  to: View;
}) {
  return (
    <a href={`#${to}`} className={`stat stat-${to}`}>
      <div className="stat-label">
        {label}
        {icon}
      </div>
      <div className="stat-value">
        {value}
        <span>{suffix}</span>
      </div>
    </a>
  );
}
function RunDetail({
  run,
  pkg,
  navigate,
}: {
  run: Run;
  pkg?: Package;
  navigate: (v: View) => void;
}) {
  const stages = ["analyze", "crawl", "index", "annotation"] as const;
  const current = run.stage === "ready" ? 4 : stages.indexOf(run.stage);
  const progress = pkg?.pairs ? Math.round((pkg.labeled / pkg.pairs) * 100) : 0;
  return (
    <section className="run-detail">
      <div className="detail-head">
        <span className="eyebrow">ВЫБРАННЫЙ ИСТОЧНИК</span>
        <Activity size={16} />
        <h2>{sourceName(run)}</h2>
        <span className="mono muted">{run.id}</span>
      </div>
      <div className="pipeline">
        {stages.map((stage, i) => (
          <div
            key={stage}
            className={`pipeline-step ${i < current ? "done" : ""} ${i === current && run.status === "running" ? "current" : ""}`}
          >
            <span className="step-node">
              {i < current ? <Check size={13} /> : i + 1}
            </span>
            <span>{stageNames[stage]}</span>
          </div>
        ))}
      </div>
      {run.error && (
        <div className="detail-error">
          <strong>Запуск остановлен</strong>
          <p>{run.error}</p>
        </div>
      )}
      {run.status === "running" && (
        <div className="activity-note">
          <span className="pulse-dot local-dot" />
          {stageNames[run.stage]}. Статус обновляется автоматически.
        </div>
      )}
      <div className="annotation-summary">
        <div className="summary-icon">
          <SquarePen size={20} />
        </div>
        <div>
          <h3>Пакет для разметки</h3>
          <small>
            {pkg
              ? `${number(pkg.pairs)} пар запрос–документ`
              : "Появится после подготовки заданий"}
          </small>
        </div>
        {pkg && (
          <span className="progress-number">
            {progress}
            <small>%</small>
          </span>
        )}
      </div>
      <div className="progress-track">
        <span style={{ width: `${progress}%` }} />
      </div>
      <div className="progress-caption">
        <span>
          {pkg?.accepted
            ? "Разметка принята · dev/test зафиксированы"
            : `${pkg?.labeled || 0} оценено · ${(pkg?.pairs || 0) - (pkg?.labeled || 0)} осталось`}
        </span>
        {pkg?.label_source === "assistant_smoke" && (
          <span className="weak-badge">SMOKE</span>
        )}
      </div>
      <div className="detail-actions">
        <button
          className="button primary"
          disabled={!pkg}
          onClick={() => navigate("annotation")}
        >
          {pkg?.accepted ? "Посмотреть разметку" : "Перейти к разметке"}
          <ArrowRight size={16} />
        </button>
        <button
          className="button"
          disabled={!run.components?.index}
          onClick={() => navigate("search")}
        >
          <Search size={16} />
          Поиск по корпусу
        </button>
      </div>
    </section>
  );
}
function NewRun({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (run: Run) => void;
}) {
  const [url, setUrl] = useState("");
  const [goal, setGoal] = useState("");
  const [budget, setBudget] = useState(20);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api<Run>("/runs", {
        method: "POST",
        body: JSON.stringify({ url, goal, max_pairs: budget }),
      });
      onCreated(result);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  return (
    <Dialog
      title="Новый запуск"
      onClose={() => {
        if (!busy) onClose();
      }}
    >

      <form onSubmit={submit}>
        <label>
          Адрес сайта
          <div className="input-icon">
            <Globe2 size={17} />
            <input
              autoFocus
              type="url"
              required
              placeholder="https://docs.example.com"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </div>
        </label>
        <label>
          Цель сбора
          <textarea
            required
            minLength={3}
            maxLength={2000}
            rows={3}
            placeholder="Например, собрать руководства и документацию для поиска по API"
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
          />
        </label>
        <label>
          Максимум пар для разметки
          <div className="budget-input">
            <input
              aria-label="Число пар"
              type="number"
              min={4}
              max={100}
              required
              value={budget}
              onChange={(e) => setBudget(Number(e.target.value))}
            />
            <span>пар запрос–документ</span>
            <ListFilter size={17} />
          </div>
        </label>
        <div className="form-note">
          <Sparkles size={17} />
          <span>
            Анализ сайта и подготовка заданий вызывают LLM. Число пар не
            ограничивает количество скачанных страниц.
          </span>
        </div>
        {error && <ErrorMessage message={error} />}
        <div className="dialog-footer">
          <button
            type="button"
            className="button"
            onClick={onClose}
            disabled={busy}
          >
            Отмена
          </button>
          <button type="submit" className="button primary" disabled={busy}>
            {busy ? <Spinner /> : <Plus size={16} />}
            {busy ? "Запускаем…" : "Начать сбор"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
