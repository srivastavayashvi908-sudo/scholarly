# Scholarly: research paper organizer 

Store your research papers, read and highlight them in the browser, and organize everything in a
hand-designed PostgreSQL database: collections, comparison tables, concept prerequisite graphs,
citation graphs, full-text and semantic search, reading stats and sharing.

**Stack:** PostgreSQL 16 + pgvector · FastAPI (Python, raw SQL via psycopg) · React + Vite

## Features

| Area | What it does |
|---|---|
| Library | Add papers by hand or **import by DOI / arXiv link** (metadata auto-filled; arXiv PDFs downloaded) |
| Reading | **In-browser PDF viewer**: select text to highlight it, tag it, colour it; highlights redraw on the page |
| Progress | Per-user status (to read / reading / done), current page, time spent (heartbeat sessions) |
| Notes & comments | Private notes per paper; **threaded comments** on highlights |
| Collections | Group papers; regroup highlights from many papers into one "virtual document" |
| Comparison | Per-collection table pivoted from EAV attributes (e.g. dataset, metric) |
| Sharing | User accounts; share collections with classmates as **viewer** or **editor** |
| Concepts | Prerequisite graph with full learning path; **cycles rejected** |
| Learn first | **AI extracts every concept a paper uses** and what each one needs, down to the basics, and merges it into your concept graph. The paper page lists what to learn first, in order, with a mini graph; tick what you already know |
| Citations | Citation graph + recursive lineage ("everything this paper builds on") |
| Read next | Papers you're ready for, given what you've already learned |
| Search | Full-text search (ranked, with highlighted snippets) across papers, highlights, notes |
| AI | Similar papers (local embeddings), **Ask your library** (RAG), AI summaries (Groq) |
| Dashboard | Totals, minutes/day, papers/month, tags, most cited, **reading streak** + activity heatmap |

## Running it

You need **Docker Desktop** and **Node.js 18+**.

```bash
# 1. Configure
cp .env.example .env          # Windows PowerShell: copy .env.example .env
#    then open .env and paste your Groq key into LLM_API_KEY (optional; see below)

# 2. Start the database + backend (first build takes a few minutes)
docker compose up -d --build

# 3. Start the frontend
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** and register an account.
API docs (interactive): **http://localhost:8000/docs**

Run the backend tests: `docker compose exec backend pytest -v`

Connect to the database with any SQL client (DBeaver, pgAdmin, `psql`):
host `localhost`, port **5433**, user/password/database `research`.

### Environment variables (`.env`)

| Variable | Required | Purpose |
|---|---|---|
| `JWT_SECRET` | yes | Signs login tokens. Any long random string. |
| `LLM_API_KEY` | for AI summaries + Ask | A Groq (`gsk_...`) or Grok/xAI (`xai-...`) key. Everything else works without it. |
| `LLM_BASE_URL` | no | Groq: `https://api.groq.com/openai/v1` · xAI: `https://api.x.ai/v1`. Any OpenAI-compatible API works. |
| `LLM_MODEL` | no | Groq: `openai/gpt-oss-120b` · xAI: a Grok model name. |
| `DATABASE_URL` | no | Set by docker-compose. When hosted: your Neon connection string. |
| `CORS_ORIGINS` | when hosted | The frontend's address, e.g. `https://scholarly.vercel.app` (comma-separate several). |

Similar papers, semantic search and embeddings use a **free local model** (`BAAI/bge-small-en-v1.5`),
so they need no key.

## Hosting it for free

| Part | Host | Settings |
|---|---|---|
| Database | [Neon](https://neon.tech) (free Postgres with pgvector) | Copy the **direct** (not pooled) connection string |
| Backend | [Render](https://render.com) free web service | *New → Blueprint* and pick this repo (uses `render.yaml`). Set `DATABASE_URL`, `LLM_API_KEY`, `CORS_ORIGINS` |
| Frontend | [Vercel](https://vercel.com) | Import the repo, root directory `frontend`, env var `VITE_API_URL` = the Render URL |

The tables are created automatically the first time the backend starts. Render's free tier sleeps
after 15 minutes idle, so the first visit after a break takes about a minute.

## Project layout

```
backend/
  migrations/001_schema.sql               all tables, constraints, generated columns
  migrations/002_views_indexes_triggers.sql  indexes, views, triggers, stored function
  migrations/003_pdf_storage.sql, 004_...    PDFs moved from disk into the database
  migrations/005_ai_concepts.sql             source ('user'/'ai') and known flags for concepts
  app/main.py        app setup + router registration
  app/db.py          connection pool + migration runner
  app/auth.py        bcrypt passwords + JWT
  app/access.py      permission checks (viewer < editor < owner)
  app/models.py      request validation (Pydantic)
  app/routes/*.py    one file per resource
  app/services/      embeddings, LLM, DOI/arXiv lookup
  tests/             pytest API tests
frontend/src/
  pages/             one file per screen
  components/        PdfViewer, HighlightsPanel, Graph, ...
```

## Database design notes (for the viva)

**Tables (21):** users, papers, paper_files, paper_reading_state, reading_sessions, collections, collection_members,
paper_collections, highlights, highlight_collections, notes, highlight_comments, paper_attributes,
concepts, concept_prerequisites, paper_concepts, citations, paper_reference_dois, paper_embeddings,
highlight_embeddings, concept_embeddings.

**Relationship patterns used**
- **One-to-many:** papers → highlights / notes; users → papers
- **Many-to-many (junction tables):** paper_collections, highlight_collections, paper_concepts, collection_members
- **Self-referencing many-to-many (graphs):** concept_prerequisites (concept → concept), citations (paper → paper)
- **Self-referencing one-to-many (tree):** highlight_comments.parent_id
- **EAV (Entity-Attribute-Value):** paper_attributes, pivoted into a table at query time
- **Weak-entity-style composite keys:** paper_reading_state (user_id, paper_id)
- **One-to-one:** papers → paper_files (uploaded PDFs stored as `bytea`, so free hosts with wiped disks keep them)

**Integrity**
- `CHECK` constraints: allowed tags/statuses/roles, colour format, year range, no self-citation,
  no self-prerequisite, `ended_at >= started_at`
- `UNIQUE`: one DOI per owner, one value per attribute per paper, unique concept names per user
- `ON DELETE CASCADE` everywhere a child row is meaningless without its parent
- **Cycle prevention** in the prerequisite graph is done in the API with a recursive query, serialized
  with `pg_advisory_xact_lock` so two concurrent inserts can't sneak a cycle in together

### The interesting SQL, and where to find it

| Concept | Where |
|---|---|
| Recursive CTE: full prerequisite chain in learning order | `routes/concepts.py` · `prerequisite_chain` |
| Recursive CTE: cycle detection before inserting an edge | `routes/concepts.py` · `add_prerequisite` |
| Recursive CTE: citation lineage with `DISTINCT ON` | `routes/citations.py` · `citation_lineage` |
| Recursive CTE: threaded comments in display order | `routes/comments.py` · `list_comments` |
| Recursive CTE + `NOT EXISTS` (relational division): what to read next | `routes/recommendations.py` |
| Recursive CTE from many start nodes: everything to learn before a paper | `routes/papers.py` · `paper_learning_path` |
| Merging AI output into the graph under one advisory lock, reusing the cycle check | `routes/concepts.py` · `merge_ai_concepts` |
| Pivot with `jsonb_object_agg ... FILTER` | `routes/collections.py` · `comparison` |
| Full-text search: generated `tsvector` columns, GIN indexes, `websearch_to_tsquery`, `ts_rank`, `ts_headline`, `UNION ALL` | `routes/search.py` |
| Vector similarity search with pgvector `<=>` + HNSW index | `routes/ai.py` · `similar_papers`, `ask_library` |
| Window functions: running total, `rank()`, percent of total | `routes/stats.py` · `overview` |
| Gaps-and-islands (streaks) with `row_number()` | `routes/stats.py` · `streak` |
| Stored SQL function + `FULL OUTER JOIN` | `activity_days()` in migration 002 |
| Triggers: `updated_at`, `finished_at` when a paper is marked done | migration 002 |
| Views for access control: `v_paper_access`, `v_paper_role` | migration 002 |
| UPSERT (`INSERT ... ON CONFLICT DO UPDATE`) | reading state, attributes, sharing, embeddings |
| Expression index `lower(doi)` | migration 002 |

Try them yourself in a SQL client, for example:

```sql
-- How many highlights per tag, per user?
SELECT u.name, t.tag, t.n FROM v_tag_counts t JOIN users u ON u.id = t.user_id ORDER BY u.name, t.n DESC;

-- See the query plan use the GIN index
EXPLAIN ANALYZE SELECT title FROM papers WHERE search @@ websearch_to_tsquery('english', 'attention');
```
