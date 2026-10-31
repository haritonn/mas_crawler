import { useEffect, useState, type FormEvent } from "react";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Files,
  Search,
} from "lucide-react";
import { api, number, type Run } from "./api";
import { Empty, ErrorMessage, ExternalLink, Spinner } from "./ui";

type Document = { url: string; title: string; text: string };
type Page = {
  documents: Document[];
  total: number;
  offset: number;
  limit: number;
};
export function Documents({ run }: { run: Run }) {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState<Page>({
    documents: [],
    total: 0,
    offset: 0,
    limit: 20,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  useEffect(() => {
    if (!run.components?.corpus) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setExpanded(null);
    api<Page>(
      `/runs/${encodeURIComponent(run.id)}/documents?offset=${offset}&limit=20&q=${encodeURIComponent(query)}`,
      { signal: controller.signal },
    )
      .then(setResult)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [run.id, run.components?.corpus, offset, query]);
  function submit(event: FormEvent) {
    event.preventDefault();
    setOffset(0);
    setQuery(input.trim());
  }
  if (!run.components?.corpus)
    return (
      <div className="panel">
        <Empty icon={<Files size={28} />} title="Корпус недоступен">
          Документы ещё не собраны или корпус был удалён. Индекс и отдельные
          пакеты могут храниться независимо.
        </Empty>
      </div>
    );
  return (
    <>
      <div className="documents-toolbar">
        <form onSubmit={submit} className="document-filter">
          <Search size={17} />
          <input
            aria-label="Фильтр документов"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Найти по заголовку или адресу…"
            maxLength={500}
          />
          <button className="button small" type="submit">
            Найти
          </button>
        </form>
        <span className="document-total">
          {number(result.total)}{" "}
          <small>документов{query ? " по фильтру" : " в корпусе"}</small>
        </span>
      </div>
      {error && <ErrorMessage message={error} />}
      {loading ? (
        <div className="loading-state">
          <Spinner />
          Читаем корпус…
        </div>
      ) : result.documents.length ? (
        <div className="corpus-documents">
          {result.documents.map((document, i) => (
            <article
              className="corpus-document panel"
              key={`${document.url}/${i}`}
            >
              <div className="corpus-document-heading">
                <span className="document-order mono">
                  {String(offset + i + 1).padStart(2, "0")}
                </span>
                <div>
                  <h2>
                    <ExternalLink url={document.url}>
                      {document.title}
                    </ExternalLink>
                  </h2>
                  <ExternalLink url={document.url}>{document.url}</ExternalLink>
                </div>
                <span className="document-length mono">
                  {number(document.text.length)} зн.
                </span>
              </div>
              <p
                className={`corpus-excerpt ${expanded === document.url ? "expanded" : ""}`}
              >
                {document.text}
              </p>
              <button
                className="text-button"
                onClick={() =>
                  setExpanded(expanded === document.url ? null : document.url)
                }
              >
                {expanded === document.url
                  ? "Свернуть документ"
                  : "Показать текст"}
                <ChevronDown
                  size={13}
                  className={expanded === document.url ? "rotate" : ""}
                />
              </button>
            </article>
          ))}
        </div>
      ) : (
        !error && (
          <div className="panel">
            <Empty icon={<Search size={26} />} title="Ничего не найдено">
              Измените фильтр. Этот раздел просматривает корпус, а поиск BM25
              находится на вкладке «Поиск».
            </Empty>
          </div>
        )
      )}
      <div className="documents-pagination">
        <span>
          {result.total
            ? `${number(offset + 1)}–${number(Math.min(offset + result.documents.length, result.total))} из ${number(result.total)}`
            : "Нет документов"}
        </span>
        <div>
          <button
            className="button small"
            disabled={loading || offset === 0}
            onClick={() => setOffset((value) => Math.max(0, value - 20))}
          >
            <ChevronLeft size={15} />
            Назад
          </button>
          <button
            className="button small"
            disabled={loading || offset + 20 >= result.total}
            onClick={() => setOffset((value) => value + 20)}
          >
            Далее
            <ChevronRight size={15} />
          </button>
        </div>
      </div>
    </>
  );
}
