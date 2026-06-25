# AGENTS.md

## Project

Single-file Streamlit app (`app.py`, ~1022 lines) that generates 3-page children's storybooks using ECNU LLM API. All business logic, DB access, and UI in one file.

## Commands

```bash
uv sync                                    # install deps
uv run streamlit run                      # start dev server (port 8501)
uv run python -c "import py_compile; py_compile.compile('app.py', doraise=True)"  # syntax check
```

No test suite exists. No linter/formatter configured. No CI.

## Architecture

- **app.py** — monolith: config → DB module → API module → business logic → Streamlit UI
- **education.db** — SQLite, auto-created at runtime (gitignored)
- **static/images/**, **static/audio/** — generated assets (gitignored)
- **pyproject.toml** — deps: numpy, requests, streamlit, python-dotenv

## ECNU API (not OpenAI SDK)

All API calls use raw `requests.post()` to `https://chat.ecnu.edu.cn/open/api/v1`. Do not add openai SDK.

| Endpoint | Model | Constraint |
|---|---|---|
| `/chat/completions` | ecnu-plus | `response_format.json_schema` for structured output |
| `/images/generations` | ecnu-image | prompt ≤ 1024 chars; URL expires in 24h |
| `/audio/speech` | ecnu-tts | input ≤ 4096 chars; returns binary mp3 |
| `/embeddings` | ecnu-embedding-small | 1024-dim vector |

Rate limits: avoid concurrent calls. 500 errors (not 429) on abuse. Quota: ~5000 credits/day.

## Database

3 tables with CASCADE deletes: `storybooks` → `storybook_pages`, `storybook_embeddings`. Foreign keys require `PRAGMA foreign_keys = ON` per connection. Embeddings stored as BLOB (`struct.pack` of float32 array).

FTS5 virtual table `storybook_fts` (content=storybook_pages) for keyword search. Indexes: `idx_storybooks_concept`, `idx_storybooks_created_at`, `idx_pages_book_id`.

## Environment

- Python 3.9+, managed by **uv** (not pip/conda)
- `.env` loaded via python-dotenv for API key (`ECNU_API_KEY`)
- Windows: GBK console encoding — avoid emoji in stdout

## Gotchas

- Image URLs from ecnu-image expire in 24h; download immediately after generation
- JSON parsing has regex fallback for LLM outputs that mix JSON with prose
- `tags` column added via ALTER TABLE migration in `init_database()` for backward compat
- No `uv.lock` regeneration needed unless changing `pyproject.toml`
