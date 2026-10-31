import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  Check,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  FileText,
  Keyboard,
  LockKeyhole,
  SquarePen,
  Undo2,
} from "lucide-react";
import {
  api,
  hostname,
  number,
  packageQuery,
  type Package,
  type Pair,
  type Run,
} from "./api";
import { Empty, ErrorMessage, ExternalLink, Spinner } from "./ui";

const grades = [
  { value: 0, label: "Не релевантен", description: "Не помогает ответить" },
  { value: 1, label: "Связан с темой", description: "Нужной информации мало" },
  { value: 2, label: "Полезен", description: "Существенная часть ответа" },
  {
    value: 3,
    label: "Точный ответ",
    description: "Полностью закрывает запрос",
  },
];

export function Annotation({
  run,
  pkg,
  refresh,
  notify,
  onEvaluate,
}: {
  run: Run;
  pkg?: Package;
  refresh: () => Promise<void>;
  notify: (text: string) => void;
  onEvaluate: () => void;
}) {
  const [pairs, setPairs] = useState<Pair[]>([]);
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [autoNext, setAutoNext] = useState(true);
  const reader = useRef<HTMLDivElement>(null);
  const lock = useRef(false);
  const base = `/runs/${encodeURIComponent(run.id)}`;
  const query = packageQuery(pkg?.id || "annotation");
  const load = useCallback(async () => {
    if (!pkg) {
      setLoading(false);
      return;
    }
    try {
      const result = await api<{ pairs: Pair[]; accepted: boolean }>(
        `${base}/pairs${query}`,
      );
      setPairs(result.pairs);
      setAccepted(result.accepted);
      const first = result.pairs.findIndex((pair) => pair.relevance === null);
      setIndex(first < 0 ? 0 : first);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [base, query, pkg?.id]);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    reader.current?.scrollTo({ top: 0 });
  }, [index]);
  const pair = pairs[index];
  const labeled = pairs.filter((p) => p.relevance !== null).length;
  async function save(value: number | null) {
    if (!pair || accepted || lock.current) return;
    lock.current = true;
    setSaving(true);
    setError("");
    try {
      await api(`${base}/pairs/${encodeURIComponent(pair.pair_id)}${query}`, {
        method: "PATCH",
        body: JSON.stringify({ relevance: value }),
      });
      setPairs((previous) =>
        previous.map((item) =>
          item.pair_id === pair.pair_id ? { ...item, relevance: value } : item,
        ),
      );
      if (autoNext && value !== null && index < pairs.length - 1)
        setIndex(index + 1);
      void refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
      lock.current = false;
    }
  }
  useEffect(() => {
    const handle = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (
        target.closest("input, textarea, select, [contenteditable]") ||
        event.metaKey ||
        event.ctrlKey ||
        event.altKey ||
        saving ||
        confirm
      )
        return;
      if (["0", "1", "2", "3"].includes(event.key) && !accepted) {
        event.preventDefault();
        void save(Number(event.key));
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        setIndex((i) => Math.min(i + 1, pairs.length - 1));
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        setIndex((i) => Math.max(i - 1, 0));
      }
    };
    window.addEventListener("keydown", handle);
    return () => window.removeEventListener("keydown", handle);
  });
  async function accept() {
    if (lock.current) return;
    lock.current = true;
    setSaving(true);
    setError("");
    try {
      await api(`${base}/accept${query}`, { method: "POST" });
      setAccepted(true);
      setConfirm(false);
      await refresh();
      notify("Разметка принята. Dev/test зафиксированы.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
      lock.current = false;
    }
  }
  if (!pkg)
    return (
      <div className="panel">
        <Empty icon={<SquarePen size={28} />} title="Пакет ещё не подготовлен">
          Дождитесь завершения генерации заданий. Готовые пакеты появятся здесь.
        </Empty>
      </div>
    );
  if (loading)
    return (
      <div className="loading-state">
        <Spinner />
        Открываем задания…
      </div>
    );
  if (!pair)
    return (
      <div className="panel">
        {error ? (
          <ErrorMessage message={error} retry={() => void load()} />
        ) : (
          <Empty icon={<FileText size={28} />} title="В пакете нет заданий">
            Проверьте результат подготовки датасета.
          </Empty>
        )}
      </div>
    );
  return (
    <>
      {error && <ErrorMessage message={error} />}
      <div className="annotation-toolbar">
        <div className="annotation-progress">
          <span>
            {number(labeled)} <small>/ {number(pairs.length)} оценено</small>
          </span>
          <div className="progress-track">
            <span style={{ width: `${(labeled / pairs.length) * 100}%` }} />
          </div>
        </div>
        <div className="annotation-tools">
          <span className="save-state" aria-live="polite">
            {saving ? (
              <>
                <Spinner />
                Сохраняем…
              </>
            ) : (
              <>
                <Check size={14} />
                {accepted ? "Зафиксировано" : "Все изменения сохранены"}
              </>
            )}
          </span>
          <a
            className="button small"
            href={`/api${base}/export${query}`}
            download
          >
            <ArrowDownToLine size={15} />
            CSV
          </a>
        </div>
      </div>
      {pkg.label_source === "assistant_smoke" && (
        <div className="notice">
          Тестовая разметка ассистента. Подходит для проверки пайплайна, но не
          для выводов о качестве поиска.
        </div>
      )}
      <div className="annotation-layout">
        <aside className="task-panel panel">
          <div className="task-heading">
            <span>Задания</span>
            <span className="count-badge">{pairs.length}</span>
          </div>
          <div className="task-list">
            {pairs.map((item, i) => (
              <button
                key={item.pair_id}
                disabled={saving}
                onClick={() => setIndex(i)}
                className={`task ${index === i ? "active" : ""}`}
                aria-label={`Задание ${i + 1}: ${item.document_title}`}
              >
                <span
                  className={`task-indicator ${item.relevance !== null ? "graded" : ""}`}
                >
                  {item.relevance !== null ? <Check size={11} /> : i + 1}
                </span>
                <span>
                  <strong>{item.document_title}</strong>
                  <small>
                    {item.query_id.toUpperCase()} · {item.pair_id}
                  </small>
                </span>
                {item.relevance !== null && (
                  <b className={`grade-chip grade-${item.relevance}`}>
                    {item.relevance}
                  </b>
                )}
              </button>
            ))}
          </div>
          <button
            className="text-button task-next"
            disabled={saving || labeled === pairs.length}
            onClick={() =>
              setIndex(pairs.findIndex((p) => p.relevance === null))
            }
          >
            К неоценённому
            <ArrowRight size={13} />
          </button>
        </aside>
        <section className="reader-panel panel">
          <div className="query-block">
            <span className="eyebrow">
              ПОИСКОВЫЙ ЗАПРОС{" "}
              <span className="mono">{pair.query_id.toUpperCase()}</span>
            </span>
            <h2>{pair.query}</h2>
            <p>Насколько документ ниже удовлетворяет этому запросу?</p>
          </div>
          <div className="document-heading">
            <div>
              <span className="eyebrow">
                ДОКУМЕНТ {index + 1} ИЗ {pairs.length}
              </span>
              <h3>{pair.document_title}</h3>
              <ExternalLink url={pair.document_url}>
                {hostname(pair.document_url)}
                {safePath(pair.document_url)}
              </ExternalLink>
            </div>
            <span className="document-icon">
              <FileText size={23} strokeWidth={1.4} />
            </span>
          </div>
          <div
            ref={reader}
            className="reader-text"
            tabIndex={0}
            aria-label="Текст документа"
          >
            {pair.document_text
              .split("§")
              .filter(Boolean)
              .map((paragraph, i) => (
                <p key={i}>{paragraph}</p>
              ))}
          </div>
          <div className="reader-pagination">
            <span className="mono">
              {pair.pair_id} / {pair.query_id}
            </span>
            <div>
              <button
                className="icon-button"
                aria-label="Предыдущий документ"
                disabled={index === 0 || saving}
                onClick={() => setIndex((i) => i - 1)}
              >
                <ChevronLeft size={18} />
              </button>
              <span>
                {index + 1}
                <small> / {pairs.length}</small>
              </span>
              <button
                className="icon-button"
                aria-label="Следующий документ"
                disabled={index === pairs.length - 1 || saving}
                onClick={() => setIndex((i) => i + 1)}
              >
                <ChevronRight size={18} />
              </button>
            </div>
          </div>
        </section>
      </div>
      <section className="grading-bar panel">
        <div className="grading-heading">
          <span>
            {accepted ? (
              <>
                <LockKeyhole size={15} />
                Оценки зафиксированы
              </>
            ) : (
              "Ваша оценка релевантности"
            )}
          </span>
          {!accepted && (
            <label className="toggle-label">
              <input
                type="checkbox"
                checked={autoNext}
                onChange={(e) => setAutoNext(e.target.checked)}
              />
              Переходить дальше
            </label>
          )}
        </div>
        <div className="grade-buttons">
          {grades.map((grade) => (
            <button
              key={grade.value}
              className={`grade-button ${pair.relevance === grade.value ? "chosen" : ""}`}
              aria-pressed={pair.relevance === grade.value}
              disabled={saving || accepted}
              onClick={() => void save(grade.value)}
            >
              <kbd>{grade.value}</kbd>
              <span>
                <strong>{grade.label}</strong>
                <small>{grade.description}</small>
              </span>
              {pair.relevance === grade.value && <Check size={16} />}
            </button>
          ))}
        </div>
        <div className="grading-footer">
          <span>
            <Keyboard size={14} />
            0–3 — оценка · ← → — документы
          </span>
          {!accepted && pair.relevance !== null && (
            <button
              className="text-button"
              disabled={saving}
              onClick={() => void save(null)}
            >
              <Undo2 size={13} />
              Снять оценку
            </button>
          )}
        </div>
      </section>
      <div className="accept-row">
        <p>
          {accepted
            ? "Dev/test уже сохранены. Можно перейти к оценке конфигураций."
            : labeled === pairs.length
              ? "Все задания оценены. Зафиксируйте разметку, чтобы перейти к метрикам."
              : "Оценки сохраняются автоматически. Можно продолжить в любое время."}
        </p>
        {accepted ? (
          <button className="button primary" onClick={onEvaluate}>
            К оценке поиска
            <ArrowRight size={16} />
          </button>
        ) : (
          <button
            className="button primary"
            disabled={labeled !== pairs.length || saving}
            onClick={() => setConfirm(true)}
          >
            <CheckCheck size={17} />
            Принять разметку
          </button>
        )}
      </div>
      {confirm && (
        <div
          className="confirm-panel panel"
          role="alertdialog"
          aria-label="Подтвердить разметку"
        >
          <div>
            <h3>Зафиксировать dev/test?</h3>
            <p>
              После приёма оценки этого пакета нельзя будет изменить в
              интерфейсе.
            </p>
          </div>
          <button
            className="button"
            disabled={saving}
            onClick={() => setConfirm(false)}
          >
            Назад
          </button>
          <button
            className="button primary"
            disabled={saving}
            onClick={() => void accept()}
          >
            {saving ? <Spinner /> : <Check size={15} />}Да, зафиксировать
          </button>
        </div>
      )}
    </>
  );
}
function safePath(url: string) {
  try {
    const path = new URL(url).pathname;
    return path.length > 65 ? `${path.slice(0, 30)}…${path.slice(-28)}` : path;
  } catch {
    return "";
  }
}
