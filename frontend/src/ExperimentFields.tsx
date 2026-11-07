import type { RetrievalExperiment } from "./api";
import { Select } from "./Select";

export function experiment(name = "BM25"): RetrievalExperiment {
  return { name, mode: "bm25", sparse_config: { title_weight: 1, text_weight: 1 }, sparse_top_k: 100, dense_top_k: 100, sparse_weight: 1, dense_weight: 1, rrf_k: 60 };
}
export function validExperiment(config: RetrievalExperiment) {
  const values = [config.sparse_config.title_weight, config.sparse_config.text_weight, config.sparse_weight, config.dense_weight];
  return !!config.name.trim() && values.every(v => Number.isFinite(v) && v >= 0) &&
    [config.sparse_top_k, config.dense_top_k].every(v => Number.isInteger(v) && v > 0) &&
    Number.isFinite(config.rrf_k) && config.rrf_k > 0 &&
    (config.mode !== "hybrid" || config.sparse_weight + config.dense_weight > 0);
}
export function ExperimentFields({ value, onChange, denseReady, modeLabel = "Режим", disabled = false }: { value: RetrievalExperiment; onChange: (value: RetrievalExperiment) => void; denseReady: boolean; modeLabel?: string; disabled?: boolean }) {
  const update = (patch: Partial<RetrievalExperiment>) => onChange({ ...value, ...patch });
  return <fieldset className="retrieval-fieldset" disabled={disabled}>
    <div className={`retrieval-fields experiment-fields experiment-fields-${value.mode}`}>
      <div className="retrieval-label"><span>{modeLabel}</span><Select label={modeLabel} variant="field" value={value.mode} disabled={disabled} onChange={mode => update({ mode: mode as RetrievalExperiment["mode"] })} options={[{ value: "bm25", label: "BM25" }, { value: "dense", label: "Dense", disabled: !denseReady }, { value: "hybrid", label: "Hybrid (RRF)", disabled: !denseReady }]} /></div>
      {value.mode !== "dense" && <>
        <label>Вес заголовка<input type="number" required min={0} step="any" value={value.sparse_config.title_weight} onChange={e => update({ sparse_config: { ...value.sparse_config, title_weight: Number(e.target.value) } })} /></label>
        <label>Вес текста<input type="number" required min={0} step="any" value={value.sparse_config.text_weight} onChange={e => update({ sparse_config: { ...value.sparse_config, text_weight: Number(e.target.value) } })} /></label>
      </>}
      {value.mode === "hybrid" && <>
        <label>Глубина BM25<input type="number" required min={1} value={value.sparse_top_k} onChange={e => update({ sparse_top_k: Number(e.target.value) })} /></label>
        <label>Глубина dense<input type="number" required min={1} value={value.dense_top_k} onChange={e => update({ dense_top_k: Number(e.target.value) })} /></label>
        <label>Вес канала BM25<input type="number" required min={0} step="any" value={value.sparse_weight} onChange={e => update({ sparse_weight: Number(e.target.value) })} /></label>
        <label>Вес канала dense<input type="number" required min={0} step="any" value={value.dense_weight} onChange={e => update({ dense_weight: Number(e.target.value) })} /></label>
        <label>Константа RRF<input type="number" required min={0.001} step="any" value={value.rrf_k} onChange={e => update({ rrf_k: Number(e.target.value) })} /></label>
      </>}
    </div>

    {value.mode === "hybrid" && value.sparse_weight + value.dense_weight === 0 && <p role="alert">Хотя бы один вес канала должен быть больше нуля.</p>}
  </fieldset>;
}
