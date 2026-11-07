import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Check, ChevronDown } from "lucide-react";

type Option = { value: string; label: string; disabled?: boolean };

export function Select({
  label,
  value,
  options,
  icon,
  onChange,
  disabled = false,
  variant = "context",
}: {
  label: string;
  value: string;
  options: Option[];
  icon?: ReactNode;
  onChange: (value: string) => void;
  disabled?: boolean;
  variant?: "context" | "field";
}) {
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const search = useRef({ text: "", time: 0 });
  const [open, setOpen] = useState(false);
  const selected = Math.max(0, options.findIndex(option => option.value === value));
  const [active, setActive] = useState(selected);
  const enabled = options.flatMap((option, index) => option.disabled ? [] : [index]);

  useEffect(() => {
    if (!open) return;
    function outside(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);

  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);

  useEffect(() => {
    if (open) document.getElementById(`${id}-${active}`)?.scrollIntoView({ block: "nearest" });
  }, [open, active, id]);

  function choose(index: number) {
    const option = options[index];
    if (!option || option.disabled || trigger.current?.matches(":disabled")) return;
    onChange(option.value);
    setOpen(false);
    trigger.current?.focus();
  }

  return (
    <div className={`context-select ${variant === "field" ? "field-select" : ""}`} ref={root}
      onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}>
      <button
        ref={trigger}
        type="button"
        className="select-trigger"
        role="combobox"
        aria-label={label}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={open ? id : undefined}
        aria-activedescendant={open && active >= 0 ? `${id}-${active}` : undefined}
        disabled={disabled}
        onClick={() => {
          setActive(options[selected]?.disabled ? enabled[0] ?? -1 : selected);
          setOpen(!open);
        }}
        onKeyDown={event => {
          if (event.currentTarget.matches(":disabled")) return;
          if (event.key === "Escape") {
            event.preventDefault();
            setOpen(false);
          } else if (event.key === "Tab") {
            setOpen(false);
          } else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
            event.preventDefault();
            setOpen(true);
            const position = enabled.indexOf(active);
            setActive(event.key === "Home" ? enabled[0] ?? -1
              : event.key === "End" ? enabled.at(-1) ?? -1
              : !open ? (options[selected]?.disabled ? enabled[0] ?? -1 : selected)
              : enabled[Math.max(0, Math.min(enabled.length - 1, position + (event.key === "ArrowDown" ? 1 : -1)))] ?? -1);
          } else if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            if (open) choose(active);
            else {
              setActive(options[selected]?.disabled ? enabled[0] ?? -1 : selected);
              setOpen(true);
            }
          } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
            const now = Date.now();
            search.current = { text: (now - search.current.time < 700 ? search.current.text : "") + event.key.toLowerCase(), time: now };
            const index = options.findIndex(option => !option.disabled && option.label.toLowerCase().startsWith(search.current.text));
            if (index >= 0) { setActive(index); setOpen(true); }
          }
        }}
      >
        {icon && <span className="select-icon" aria-hidden="true">{icon}</span>}
        <span className="select-value">{options[selected]?.label}</span>
        <ChevronDown size={13} className={open ? "rotate" : ""} aria-hidden="true" />
      </button>
      {open && !disabled && <div className="select-menu" id={id} role="listbox" aria-label={label}>
        {options.map((option, index) => <div key={option.value} id={`${id}-${index}`} role="option"
          aria-selected={option.value === value} aria-disabled={option.disabled || undefined}
          className={`select-option ${index === active ? "active" : ""}`}
          onPointerMove={() => { if (!option.disabled) setActive(index); }}
          onMouseDown={event => event.preventDefault()} onClick={() => choose(index)}>
          <span>{option.label}</span>
          {option.value === value && <Check size={13} aria-hidden="true" />}
        </div>)}
      </div>}
    </div>
  );
}
