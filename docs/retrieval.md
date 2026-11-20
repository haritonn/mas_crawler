# Поиск и экспорт

[← Обзор проекта](../README.md)

| Режим | Устройство | Что настраивается |
| --- | --- | --- |
| BM25 | Tantivy по заголовкам и тексту | Веса полей (`title_weight`, `text_weight`), по умолчанию `1.0` / `1.0` |
| Dense | Sentence Transformers, поиск в Qdrant | Модель, префиксы, разбиение текста; при построении — устройство и batch |
| Hybrid | Взвешенный RRF поверх BM25 и Dense | Глубины кандидатов, веса каналов и константа RRF |

В Gather выберите источник с корпусом и индексом. Dense готовится на странице «Поиск» или в «Источники → Состав». Затем на странице «Поиск» можно переключать режимы; раскрытый результат Hybrid показывает ранги и оценки обоих каналов. Без Qdrant остаётся BM25.

## BM25

```bash
just search --index runs/from-plan/index --query "std::ffi" --top-k 5
```

Запрос — обычный текст, а не язык запросов Tantivy: `title:Iterator`, кавычки и `AND`/`OR` не включают расширенный синтаксис. Для других весов CLI принимает JSON через `--config`. `just experiment` возвращает выдачи нескольких конфигураций; оценка по разметке описана [отдельно](evaluation.md).

```python
import json
from mas_crawler import SearchIndex

index = SearchIndex("runs/from-plan/index")
hits = json.loads(index.search("Iterator", top_k=5))
```

`SearchIndex` переиспользует открытый индекс; `search` и `run_experiments` возвращают JSON-строки. Полный цикл сборки доступен через `build_search_system`, отдельный обход — через `crawl_site`.

## Dense

Запустите Qdrant (`docker compose -f compose.qdrant.yaml up -d`) и дождитесь ответа `200` от `http://127.0.0.1:6333/readyz`. Compose публикует Qdrant только на loopback, данные сохраняет в volume. Альтернативный адрес задаётся через `QDRANT_URL` для Gather или `--qdrant-url` для команд `upload` и `search`.

Пример `profile.json` для технической проверки на английском корпусе:

```json
{"model_id": "sentence-transformers/all-MiniLM-L6-v2", "normalize_embeddings": true}
```

```bash
just dense build --corpus runs/from-plan/corpus.jsonl \
  --profile profile.json --output runs/dense-01 --device cpu
just dense upload --build runs/dense-01
just dense search --build runs/dense-01 --query "Iterator" --top-k 5
```

Первая загрузка модели требует сети и места на диске, но не платного API. Профиль должен подходить языку корпуса. Поддерживается обычный Transformer-вход с fast-токенизатором, без Router, query expansion и пользовательского remote code. Размер и перекрытие окна задаются через `--chunk-size` и `--overlap`, batch — через `--batch-size`. Превышение лимита модели с учётом префикса и специальных токенов вызывает ошибку, а не тихую обрезку.

Сборка пишет `chunks.jsonl`, `embeddings.npy`, копию `model/` и итоговый `build.json`. Кодируется текст фрагмента; заголовок остаётся метаданными. Qdrant хранит отдельную коллекцию для сборки. Повторный `upload` той же сборки не создаёт дубликатов, `search` группирует чанки по URL и возвращает лучший фрагмент документа. Во всех режимах больший score лучше (для Euclidean это отрицательное расстояние).

Публичный API: `mas_crawler.dense.{EmbeddingProfile, build_dense, upload_dense, DenseSearch}`. Корпус загружается в память целиком, матрица записывается батчами. Автовозобновления построения нет; загрузку в Qdrant можно повторить отдельно. UI не подхватывает CLI-сборки автоматически. Неудачная пересборка в UI не заменяет прежнюю, а изменение корпуса делает прежнюю сборку непригодной для новых запросов.

## Hybrid

```bash
just hybrid --index runs/from-plan/index --build runs/dense-01 \
  --query "Iterator" --top-k 10 \
  --sparse-top-k 100 --dense-top-k 100 \
  --sparse-weight 1 --dense-weight 1 --rrf-k 60
```

Оба индекса должны быть построены из одного корпуса, Dense — заранее загружен в Qdrant. В CLI соответствие обеспечивает вызывающая сторона. В UI Dense привязан к SHA-256 корпуса, но соответствие уже существующего индекса Tantivy остаётся предпосылкой.

`HybridSearch` объединяет результаты по точному URL. Формула вклада канала — `weight / (rrf_k + rank)` с рангами от единицы; исходные scores не суммируются. Дубликаты URL удаляются до назначения позиций, равный итоговый score разрешается по URL. Нулевой вес отключает вызов канала, хотя бы один вес должен быть положительным. Ошибка активного канала не приводит к тихому переходу на другой режим.

В Python переиспользуйте открытые `SearchIndex` и `DenseSearch` с `HybridSearch`; CLI открывает их для каждого запуска. `mas_crawler.hybrid.rrf_fusion` объединяет готовые выдачи без загрузки модели.

## Экспорт BM25

В Gather откройте сохранённое сравнение на странице «Оценка» и нажмите «Экспорт» у выбранного **BM25**-эксперимента. ZIP содержит полный корпус, исходники самостоятельного FastAPI/Tantivy-сервиса, `search.toml` с выбранными весами, Dockerfile, инструкцию запуска и `export.json` с происхождением эксперимента, включая тип разметки. Сервис не зависит от Gather и LLM; индекс строится при развёртывании. Готового UI поиска в архиве нет.

- После изменения корпуса нужно новое сравнение. Dense, Hybrid и прямой экспорт из отчёта оптимизации пока не поддерживаются.
- Python API: `mas_crawler.exporting.export_project(corpus, experiment, output, corpus_sha256=..., name=...)`, где `experiment` — `RetrievalExperiment`, а SHA-256 берётся из отчёта. Существующий ZIP не перезаписывается. Экспорт сам по себе не вызывает LLM, Cargo или Docker.
- Экспорт не переоценивает качество. После пересборки индекса порядок документов с одинаковым score может отличаться.

Подробности запуска — в [README шаблона](../templates/search-service/README.md). Для разработчиков: после изменений в [`core/src/search.rs`](../core/src/search.rs) выполните `python tools/sync_search_template.py` и тесты шаблона. Проверка синхронизации без записи: `python tools/sync_search_template.py --check`.
