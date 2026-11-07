import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, number, type DenseProfile, type RetrievalJob, type RetrievalState, type Run } from "./api";
import { ErrorMessage, Spinner } from "./ui";
import { Select } from "./Select";
import "./retrieval.css";

/** Sequential polling: aborts on unmount/refresh, never overlaps reads. */
export function useRetrieval(runId: string) {
  const [state, setState] = useState<RetrievalState | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function read() {
      try {
        const next = await api<RetrievalState>(`/runs/${encodeURIComponent(runId)}/retrieval`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setState(next);
        setError("");
        timer = setTimeout(() => void read(), next.active_job?.status === "running" || next.dense.status === "running" ? 1000 : 5000);
      } catch (e) {
        if (controller.signal.aborted) return;
        setError((e as Error).message);
        timer = setTimeout(() => void read(), 5000);
      }
    }
    void read();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [runId, revision]);
  return { state, error, refresh: () => setRevision(v => v + 1) };
}
export type RetrievalResource = ReturnType<typeof useRetrieval>;
export function denseAvailable(resource: RetrievalResource) {
  return !resource.error && !!resource.state?.dense.ready && !!resource.state.qdrant.available;
}

export function JobProgress({ job }: { job: RetrievalJob }) {
  return <div className="retrieval-progress" role="status">
    <strong>{job.status === "running" ? "Выполняется" : job.status === "ready" ? "Завершено" : job.status === "interrupted" ? "Прервано" : "Ошибка"}</strong>
    <span className="mono">{job.stage} · {job.completed} / {job.total ?? "?"}</span>
    {job.status === "running" && <progress aria-label="Прогресс операции" value={job.total ? job.completed : undefined} max={job.total || undefined} />}
    {job.error && <ErrorMessage message={job.error} />}
  </div>;
}

export function DensePanel({ run, resource, onActive }: { run: Run; resource?: RetrievalResource; onActive?: (id: string, active: boolean) => void }) {
  // Wrapper keeps one status reader per mounted panel or owning page.
  return resource ? <DensePanelForm key={run.id} run={run} resource={resource} onActive={onActive} /> : <DensePanelWithStatus key={run.id} run={run} onActive={onActive} />;
}
function DensePanelWithStatus({ run, onActive }: { run: Run; onActive?: (id: string, active: boolean) => void }) {
  const resource = useRetrieval(run.id);
  return <DensePanelForm run={run} resource={resource} onActive={onActive} />;
}
function DensePanelForm({ run, resource, onActive }: { run: Run; resource: RetrievalResource; onActive?: (id: string, active: boolean) => void }) {
  const { state, error, refresh } = resource;
  const [profile, setProfile] = useState<DenseProfile>({ model_id: "intfloat/multilingual-e5-small", normalize_embeddings: true, query_prompt: "query: ", document_prompt: "passage: ", max_seq_length: null, similarity: "cosine" });
  const [device, setDevice] = useState("cpu");
  const [chunkSize, setChunkSize] = useState(192);
  const [overlap, setOverlap] = useState(32);
  const [batchSize, setBatchSize] = useState(32);
  const [pending, setPending] = useState(false);
  const [submitted, setSubmitted] = useState<RetrievalJob | null>(null);
  const [submitError, setSubmitError] = useState("");
  const dirty = useRef(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (state?.dense.profile && !dirty.current) setProfile(state.dense.profile);
  }, [state?.dense.profile]);
  const currentJob = state?.active_job || state?.dense.job;
  const job = submitted && (!currentJob || currentJob.id !== submitted.id) ? submitted : currentJob;
  const active = pending || job?.status === "running";
  useEffect(() => { onActive?.(run.id, !!active); }, [run.id, active, onActive]);
  useEffect(() => {
    if (submitted && (currentJob?.id === submitted.id || state?.dense.build_id === submitted.id)) setSubmitted(null);
  }, [currentJob, state?.dense.build_id, submitted]);
  const changeProfile = (patch: Partial<DenseProfile>) => { dirty.current = true; setProfile(p => ({ ...p, ...patch })); };
  async function build(event: FormEvent) {
    event.preventDefault();
    if (active || !state?.qdrant.available || !run.components?.corpus) return;
    if (overlap >= chunkSize) { setSubmitError("Перекрытие должно быть меньше размера чанка."); return; }
    const abort = new AbortController();
    controller.current = abort;
    setPending(true); setSubmitError("");
    try {
      const next = await api<RetrievalJob>(`/runs/${encodeURIComponent(run.id)}/dense`, { method: "POST", signal: abort.signal, body: JSON.stringify({ profile, device, chunk_size: chunkSize, overlap, batch_size: batchSize }) });
      if (abort.signal.aborted) return;
      setSubmitted(next);
      refresh();
    } catch (e) { if (!abort.signal.aborted) setSubmitError((e as Error).message); }
    finally { if (!abort.signal.aborted) setPending(false); }
  }
  return <section className="dense-panel panel" aria-label="Подготовка dense">
    <div className="section-heading"><h2>Подготовка dense</h2>
      <button type="button" className="text-button" onClick={refresh}>Обновить статус</button></div>
    {!state && !error && <div className="loading-state"><Spinner />Проверяем dense и Qdrant…</div>}
    {error && <ErrorMessage message={error} retry={refresh} />}
    {state && <>
      <div className="retrieval-status" role="status"><strong>{state.dense.ready ? "Dense готов" : state.dense.error ? "Dense недоступен" : state.dense.status === "absent" ? "Dense ещё не подготовлен" : `Dense: ${state.dense.status}`}</strong>
        <span role={state.qdrant.available ? undefined : "alert"}>{state.qdrant.available ? "Qdrant доступен" : "Qdrant недоступен"}</span>
        {state.dense.ready && <span>{number(state.dense.documents)} документов · {number(state.dense.chunks)} чанков</span>}
      </div>
      {state.qdrant.available && state.dense.error && <p className="notice" role="alert">{state.dense.error}</p>}

    </>}
    {job && job.status !== "ready" && <JobProgress job={job} />}
    {!run.components?.corpus && <p className="notice">Сначала нужен собранный корпус документов.</p>}
    <form onSubmit={build}>
      <fieldset disabled={active} className="retrieval-fieldset">
        <div className="retrieval-fields">
          <label className="wide-field">Модель embeddings<input required value={profile.model_id} onChange={e => changeProfile({ model_id: e.target.value })} /></label>
          <div className="retrieval-label"><span>Устройство</span><Select label="Устройство" variant="field" value={device} disabled={active} onChange={setDevice} options={[{ value: "cpu", label: "CPU" }, { value: "cuda", label: "CUDA" }, { value: "mps", label: "MPS" }]} /></div>
          <div className="retrieval-label"><span>Сходство</span><Select label="Сходство" variant="field" value={profile.similarity || "cosine"} disabled={active} onChange={similarity => changeProfile({ similarity: similarity as DenseProfile["similarity"] })} options={[{ value: "cosine", label: "Cosine" }, { value: "dot", label: "Dot" }, { value: "euclidean", label: "Euclidean" }]} /></div>
          <label>Размер чанка<input type="number" required min={1} value={chunkSize} onChange={e => setChunkSize(Number(e.target.value))} /></label>
          <label>Перекрытие<input type="number" required min={0} max={Math.max(0, chunkSize - 1)} value={overlap} onChange={e => setOverlap(Number(e.target.value))} /></label>
          <label>Размер batch<input type="number" required min={1} value={batchSize} onChange={e => setBatchSize(Number(e.target.value))} /></label>
          <label>Макс. длина модели<input type="number" min={1} placeholder="По умолчанию" value={profile.max_seq_length ?? ""} onChange={e => changeProfile({ max_seq_length: e.target.value ? Number(e.target.value) : null })} /></label>
          <label className="wide-field">Префикс запроса<input disabled={profile.query_prompt == null} value={profile.query_prompt ?? ""} onChange={e => changeProfile({ query_prompt: e.target.value })} /></label>
          <label className="wide-field">Префикс документа<input disabled={profile.document_prompt == null} value={profile.document_prompt ?? ""} onChange={e => changeProfile({ document_prompt: e.target.value })} /></label>
          <label className="checkbox-field"><input type="checkbox" checked={profile.query_prompt == null} onChange={e => changeProfile({ query_prompt: e.target.checked ? null : "" })} />Автопрефикс запроса из модели</label>
          <label className="checkbox-field"><input type="checkbox" checked={profile.document_prompt == null} onChange={e => changeProfile({ document_prompt: e.target.checked ? null : "" })} />Автопрефикс документа из модели</label>
          <label className="checkbox-field"><input type="checkbox" checked={profile.normalize_embeddings ?? true} onChange={e => changeProfile({ normalize_embeddings: e.target.checked })} />Нормализация embeddings</label>
        </div>
      </fieldset>

      {submitError && <ErrorMessage message={submitError} />}
      <div className="retrieval-actions"><button className="button primary" disabled={active || !state || !!error || !state.qdrant.available || !run.components?.corpus || !profile.model_id.trim()}>{active ? <Spinner /> : null}{active ? "Операция выполняется…" : state?.dense.ready ? "Пересобрать dense" : job?.status === "failed" || job?.status === "interrupted" ? "Повторить подготовку dense" : "Подготовить dense"}</button></div>
    </form>
  </section>;
}
