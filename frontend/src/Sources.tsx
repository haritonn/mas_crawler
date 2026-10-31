import { useState, type FormEvent } from "react";
import {
  Archive,
  ArrowRight,
  Check,
  ChevronDown,
  Database,
  FileJson,
  Files,
  FolderOpen,
  Globe2,
  Pencil,
  RotateCcw,
  Search,
  ShieldAlert,
  SquarePen,
  Trash2,
} from "lucide-react";
import { api, hostname, number, sourceName, type Run, type View } from "./api";
import { Dialog, Empty, ErrorMessage, Spinner, Status } from "./ui";

type Removal = {
  run: Run;
  component: "all" | "corpus" | "index" | "plan" | "package";
  package?: string;
  title: string;
  warning: string;
};
type Props = {
  runs: Run[];
  refresh: () => Promise<void>;
  notify: (text: string) => void;
  onOpen: (id: string, view: View) => void;
};
export function Sources({ runs, refresh, notify, onOpen }: Props) {
  const [filter, setFilter] = useState("");
  const [archived, setArchived] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<Run | null>(null);
  const [removal, setRemoval] = useState<Removal | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const visible = runs.filter(
    (run) =>
      Boolean(run.archived) === archived &&
      `${sourceName(run)} ${run.url} ${run.id}`
        .toLowerCase()
        .includes(filter.toLowerCase()),
  );
  async function archive(run: Run) {
    setBusy(run.id);
    setError("");
    try {
      await api(`/runs/${encodeURIComponent(run.id)}`, {
        method: "PATCH",
        body: JSON.stringify({ archived: !run.archived }),
      });
      await refresh();
      notify(
        run.archived
          ? "Источник восстановлен."
          : "Источник убран из списка. Все файлы сохранены.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }
  return (
    <>
      <div className="library-toolbar">
        <div className="segmented" aria-label="Фильтр источников">
          <button
            className={!archived ? "active" : ""}
            onClick={() => setArchived(false)}
          >
            Активные<span>{runs.filter((run) => !run.archived).length}</span>
          </button>
          <button
            className={archived ? "active" : ""}
            onClick={() => setArchived(true)}
          >
            Убранные<span>{runs.filter((run) => run.archived).length}</span>
          </button>
        </div>
        <div className="compact-search library-search">
          <Search size={15} />
          <input
            aria-label="Поиск по локальным источникам"
            placeholder="Название, адрес или ID…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>
      </div>
      {error && <ErrorMessage message={error} />}
      <div className="source-library">
        {visible.map((run, i) => {
          const locked = run.status === "running" || busy === run.id;
          const open = expanded === run.id;
          return (
            <article
              key={run.id}
              className={`source-record panel tint-${i % 3}`}
            >
              <div className="record-heading">
                <span className="record-icon">
                  <Globe2 size={22} strokeWidth={1.5} />
                </span>
                <div className="record-title">
                  <h2>{sourceName(run)}</h2>
                  <span>
                    {hostname(run.url)}
                    <span className="separator">/</span>
                    <span className="mono">{run.id}</span>
                  </span>
                </div>
                {run.archived ? (
                  <span className="archived-label">
                    <Archive size={12} />
                    Убран из списка
                  </span>
                ) : (
                  <Status run={run} />
                )}
                <div className="record-tools">
                  <button
                    className="icon-button"
                    aria-label={`Переименовать ${run.id}`}
                    title="Переименовать"
                    disabled={locked}
                    onClick={() => setRenaming(run)}
                  >
                    <Pencil size={15} />
                  </button>
                  <button
                    className="icon-button"
                    aria-label={
                      run.archived
                        ? `Восстановить ${run.id}`
                        : `Убрать из списка ${run.id}`
                    }
                    title={
                      run.archived
                        ? "Восстановить"
                        : "Убрать из списка, сохранив файлы"
                    }
                    disabled={locked}
                    onClick={() => void archive(run)}
                  >
                    {run.archived ? (
                      <RotateCcw size={15} />
                    ) : (
                      <Archive size={15} />
                    )}
                  </button>
                  <button
                    className="icon-button danger-icon"
                    aria-label={`Удалить всю цепочку ${run.id}`}
                    title="Удалить источник и все его файлы"
                    disabled={locked}
                    onClick={() =>
                      setRemoval({
                        run,
                        component: "all",
                        title: "Удалить всю цепочку?",
                        warning:
                          "Будет безвозвратно удалён весь каталог этого запуска: план, корпус, индекс, все пакеты разметки, dev/test и отчёты.",
                      })
                    }
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
              <p className="record-goal">
                {run.goal || "Сбор по сохранённому плану обхода."}
              </p>
              <div className="record-footer">
                <div className="record-counts">
                  <span>
                    <Files size={14} />
                    {number(run.documents)} документов
                  </span>
                  <span>
                    <SquarePen size={14} />
                    {number(run.labeled)} / {number(run.pairs)} оценок
                  </span>
                </div>
                <div className="record-links">
                  <button
                    className="text-button"
                    disabled={run.archived || !run.components?.corpus}
                    onClick={() => onOpen(run.id, "documents")}
                  >
                    Документы
                    <ArrowRight size={13} />
                  </button>
                  <button
                    className="text-button"
                    disabled={run.archived || !run.components?.index}
                    onClick={() => onOpen(run.id, "search")}
                  >
                    Поиск
                    <ArrowRight size={13} />
                  </button>
                  <button
                    className="text-button"
                    disabled={run.archived || !run.packages.length}
                    onClick={() => onOpen(run.id, "annotation")}
                  >
                    Разметка
                    <ArrowRight size={13} />
                  </button>
                </div>
                <button
                  className="component-toggle"
                  aria-expanded={open}
                  onClick={() => setExpanded(open ? null : run.id)}
                >
                  <FolderOpen size={14} />
                  Состав
                  <ChevronDown size={14} className={open ? "rotate" : ""} />
                </button>
              </div>
              {open && (
                <div className="component-list">
                  <div className="component-list-heading">
                    <span>Файлы этого запуска</span>
                    <span>Удаление компонентов не запускает их пересборку</span>
                  </div>
                  <Component
                    icon={<FileJson size={17} />}
                    name="План обхода"
                    path="crawl-plan.json"
                    exists={!!run.components?.plan}
                    locked={locked}
                    onDelete={() =>
                      setRemoval({
                        run,
                        component: "plan",
                        title: "Удалить план обхода?",
                        warning:
                          "Удалится только crawl-plan.json. Корпус, индекс и разметка сохранятся.",
                      })
                    }
                  />
                  <Component
                    icon={<Files size={17} />}
                    name="Корпус документов"
                    path="corpus.jsonl"
                    exists={!!run.components?.corpus}
                    locked={locked}
                    onDelete={() =>
                      setRemoval({
                        run,
                        component: "corpus",
                        title: "Удалить корпус и зависимые данные?",
                        warning:
                          "Вместе с корпусом удалятся индекс, все пакеты разметки, dev/test и отчёты сбора. План обхода останется.",
                      })
                    }
                  />
                  <Component
                    icon={<Database size={17} />}
                    name="Поисковый индекс"
                    path="index/"
                    exists={!!run.components?.index}
                    locked={locked}
                    onDelete={() =>
                      setRemoval({
                        run,
                        component: "index",
                        title: "Удалить поисковый индекс?",
                        warning:
                          "Корпус и разметка сохранятся. Поиск и оценка станут недоступны до пересборки индекса через CLI.",
                      })
                    }
                  />
                  {run.packages.map((pkg) => (
                    <Component
                      key={pkg.id}
                      icon={<SquarePen size={17} />}
                      name={`Пакет ${pkg.id}`}
                      path={`${pkg.id}/ · ${pkg.pairs} пар${pkg.accepted ? " · dev/test" : ""}`}
                      exists
                      locked={locked}
                      onDelete={() =>
                        setRemoval({
                          run,
                          component: "package",
                          package: pkg.id,
                          title: `Удалить пакет ${pkg.id}?`,
                          warning:
                            "Удалится этот пакет целиком: задания, оценки, dev/test и его отчёты. Корпус, индекс и остальные пакеты сохранятся.",
                        })
                      }
                    />
                  ))}
                </div>
              )}
            </article>
          );
        })}
      </div>
      {!visible.length && (
        <div className="panel">
          <Empty
            icon={<Database size={28} />}
            title={
              archived
                ? "Здесь будут убранные источники"
                : filter
                  ? "Источники не найдены"
                  : "Пока нет локальных источников"
            }
          >
            {archived
              ? "Убранные из списка источники сохраняют все файлы. Их можно вернуть в работу в любой момент."
              : "Создайте новый запуск или измените поисковый фильтр."}
          </Empty>
        </div>
      )}
      <div className="library-note">
        <Archive size={15} />
        <p>
          «Убрать из списка» сохраняет файлы и позволяет восстановить источник.
          Корзина удаляет данные с диска — только после подтверждения ID.
        </p>
      </div>
      {renaming && (
        <Rename
          run={renaming}
          onClose={() => setRenaming(null)}
          onDone={async () => {
            setRenaming(null);
            await refresh();
            notify("Название источника обновлено.");
          }}
        />
      )}
      {removal && (
        <DeleteComponent
          removal={removal}
          onClose={() => setRemoval(null)}
          onDone={async () => {
            setRemoval(null);
            await refresh();
            notify("Выбранные данные удалены.");
          }}
        />
      )}
    </>
  );
}
function Component({
  icon,
  name,
  path,
  exists,
  locked,
  onDelete,
}: {
  icon: React.ReactNode;
  name: string;
  path: string;
  exists: boolean;
  locked: boolean;
  onDelete: () => void;
}) {
  return (
    <div className={`component-row ${!exists ? "missing" : ""}`}>
      <span className="component-icon">{icon}</span>
      <div>
        <strong>{name}</strong>
        <small className="mono">{path}</small>
      </div>
      <span className="component-state">
        {exists ? (
          <>
            <Check size={11} />
            На диске
          </>
        ) : (
          "Отсутствует"
        )}
      </span>
      <button
        className="icon-button danger-icon"
        aria-label={`Удалить ${name}`}
        disabled={locked || !exists}
        onClick={onDelete}
      >
        <Trash2 size={14} />
      </button>
    </div>
  );
}
function Rename({
  run,
  onClose,
  onDone,
}: {
  run: Run;
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const [name, setName] = useState(sourceName(run));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api(`/runs/${encodeURIComponent(run.id)}`, {
        method: "PATCH",
        body: JSON.stringify({ name: name.trim() }),
      });
      await onDone();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  return (
    <Dialog
      title="Понятное имя источника."
      eyebrow="ПЕРЕИМЕНОВАНИЕ"
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <p className="dialog-description">
        Название изменится только в интерфейсе. Каталог, пути и данные останутся
        прежними.
      </p>
      <form onSubmit={submit}>
        <label>
          Название источника
          <input
            autoFocus
            required
            maxLength={100}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        {error && <ErrorMessage message={error} />}
        <div className="dialog-footer">
          <button
            type="button"
            className="button"
            disabled={busy}
            onClick={onClose}
          >
            Отмена
          </button>
          <button className="button primary" disabled={busy || !name.trim()}>
            {busy ? <Spinner /> : <Check size={15} />}Сохранить название
          </button>
        </div>
      </form>
    </Dialog>
  );
}
function DeleteComponent({
  removal,
  onClose,
  onDone,
}: {
  removal: Removal;
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api(`/runs/${encodeURIComponent(removal.run.id)}/delete`, {
        method: "POST",
        body: JSON.stringify({
          component: removal.component,
          package: removal.package,
          confirm: confirmation,
        }),
      });
      await onDone();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  return (
    <Dialog
      title={removal.title}
      eyebrow="УДАЛЕНИЕ С ДИСКА"
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <div className="destructive-warning">
        <ShieldAlert size={20} />
        <p>{removal.warning}</p>
      </div>
      <p className="dialog-description">
        Это действие нельзя отменить. Для подтверждения введите ID:
        <code className="confirmation-id">{removal.run.id}</code>
      </p>
      <form onSubmit={submit}>
        <label>
          ID источника
          <input
            autoFocus
            autoComplete="off"
            required
            value={confirmation}
            onChange={(e) => setConfirmation(e.target.value)}
          />
        </label>
        {error && <ErrorMessage message={error} />}
        <div className="dialog-footer">
          <button
            type="button"
            className="button"
            disabled={busy}
            onClick={onClose}
          >
            Отмена
          </button>
          <button
            className="button destructive"
            disabled={busy || confirmation !== removal.run.id}
          >
            {busy ? <Spinner /> : <Trash2 size={15} />}Удалить безвозвратно
          </button>
        </div>
      </form>
    </Dialog>
  );
}
