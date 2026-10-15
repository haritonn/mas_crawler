## MAS Crawler

### Rust CLI

Команды выполняются из корня репозитория. Сбор корпуса:

```bash
cargo run --manifest-path core/Cargo.toml -- collect \
  --urls core/urls.txt \
  --config core/scraper-config.json \
  --output core/corpus.jsonl
```

Построение индекса по существующему JSONL-корпусу:

```bash
cargo run --manifest-path core/Cargo.toml -- index \
  --corpus core/corpus.jsonl \
  --index core/search-index
```

Поиск без повторной загрузки страниц и построения индекса:

```bash
cargo run --manifest-path core/Cargo.toml -- search \
  --index core/search-index \
  --query "CSS selectors" \
  --top-k 5
```

`search` выводит в stdout JSON-массив объектов с полями `url`, `title`, `score`.
Диагностика выводится в stderr; ошибки завершают команду с ненулевым кодом.
Пустой запрос, отсутствие совпадений или `--top-k 0` дают `[]`.
Запрос поддерживает синтаксис Tantivy QueryParser; некорректный синтаксис считается ошибкой.

`collect` не перезаписывает существующий выходной файл, а `index` требует новый
каталог индекса с существующим родительским каталогом. Корпус содержит по одному
объекту `{"url":"...","title":"...","text":"..."}` на строку; пустые строки
пропускаются. Ошибка JSON или структуры документа указывает номер строки.
Пример предполагает, что список URL, конфигурация и корпус подготовлены локально.

Справка: `cargo run --manifest-path core/Cargo.toml -- --help`.

### Проверки

```bash
cargo test --manifest-path core/Cargo.toml --locked
cargo clippy --manifest-path core/Cargo.toml --locked --all-targets -- -D warnings
```

Тесты CLI используют локальный HTTP-сервер и временные файлы, не обращаясь к docs.rs.
