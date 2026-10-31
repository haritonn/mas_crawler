import { useEffect, useId, useRef, type ReactNode } from "react";
import { AlertCircle, ArrowUpRight, Check, Loader2, X } from "lucide-react";
import { safeUrl, type Run } from "./api";

export function Spinner() {
  return <Loader2 size={16} className="spin" aria-label="Загрузка" />;
}
export function ErrorMessage({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return (
    <div className="error-box" role="alert">
      <AlertCircle size={18} />
      <span>{message}</span>
      {retry && (
        <button className="text-button" onClick={retry}>
          Повторить
        </button>
      )}
    </div>
  );
}
export function Empty({
  icon,
  title,
  children,
  action,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action && <div className="empty-actions">{action}</div>}
    </div>
  );
}
export function ExternalLink({
  url,
  children,
}: {
  url: string;
  children: ReactNode;
}) {
  const href = safeUrl(url);
  return href ? (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="external"
    >
      {children}
      <ArrowUpRight size={13} />
    </a>
  ) : (
    <span>{children}</span>
  );
}
const labels: Record<Run["status"], string> = {
  running: "В работе",
  ready: "Готово",
  failed: "Ошибка",
  interrupted: "Прервано",
  collected: "Корпус готов",
};
export function Status({ run }: { run: Run }) {
  return (
    <span className={`status status-${run.status}`}>
      <span className={run.status === "running" ? "pulse-dot" : ""}>
        {run.status === "ready" ? <Check size={11} /> : <i />}
      </span>
      {labels[run.status]}
    </span>
  );
}
export function Dialog({
  title,
  onClose,
  children,
  eyebrow = "НОВЫЙ ИСТОЧНИК",
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  eyebrow?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const node = ref.current;
    node?.showModal();
    return () => node?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="dialog"
      aria-labelledby={titleId}
      onCancel={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="dialog-heading">
        <div>
          <span className="eyebrow">{eyebrow}</span>
          <h2 id={titleId}>{title}</h2>
        </div>
        <button className="icon-button" aria-label="Закрыть" onClick={onClose}>
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
