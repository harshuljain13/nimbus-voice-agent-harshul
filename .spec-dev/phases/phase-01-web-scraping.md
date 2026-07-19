# Phase 1 — Web Scraping (Report / Design Doc)

> Status: ✅ Done · Requirement: R1 · Tests: 5 passing · Playground panel: "Phase 1 · Web scraping"

## 1. Concept — what this phase teaches

An LLM knows nothing about *Nimbus* — it's a made-up company. To answer questions about it,
we must **give the model the facts**. That's "grounding." There are two ways to feed facts,
and this project builds both:

- **RAGless**: paste *all* the facts into the prompt every time (one big `context.md`).
  Simple, but the prompt gets huge.
- **RAG**: store the facts as many small **chunks**, and at question time fetch only the few
  relevant chunks. Efficient, but more machinery.

**Both start from the same clean text.** So Phase 1's job is turning the raw catalog
(`catalog.json`) into **clean, readable documents** — the shared raw material for RAGless
(later a single `context.md`) and RAG (later chopped into chunks).

Teaching point: **garbage in, garbage out.** If the source text is messy, retrieval and
answers are messy. Time spent making the corpus clean pays off in every later phase.

## 2. What we built

```
backend/app/scraping/
  paths.py          where the catalog is and where docs go
  render.py         functions that turn catalog data → markdown (one per topic)
  scrape.py         reads catalog.json, writes docs/*.md, returns a manifest
  build_context.py  concatenates docs/*.md → one context.md (the RAGless payload)
backend/data/docs/  generated: company, families, pricing, monthly-vs-annual, refund,
                    terms, faq, + products/<id>.md  (24 products)
backend/data/context.md   generated: everything stitched together (~104k chars)
```

Endpoints (all driven from the playground): `POST /scrape`, `POST /build-context`,
`GET /corpus`, `GET /corpus/file?name=...`.

Output: **31 docs** = 24 product docs + 7 topic docs (FAQ, Pricing, Families, Refund, T&C,
Monthly-vs-Annual, Company).

## 3. Design decisions

| Decision | Choice | Why |
|---|---|---|
| Source | `catalog.json` (not HTML scraping) | The site is *driven by* this JSON — it's the clean source of truth. HTML scraping is a noisy fallback (deferred). |
| Doc granularity | one file per product + one per policy topic | Matches how people ask ("tell me about Nimbus CRM", "what's the refund policy") and gives RAG natural chunk boundaries |
| Format | Markdown | Human-readable, and headings/tables give structure the chunker can use later |
| Derived docs | compute `monthly-vs-annual` savings, `pricing` tables, `families` grouping | The agent shouldn't have to do arithmetic the docs can state directly |
| `context.md` | ordered concatenation with `---` separators | RAGless needs one payload; ordering (company→pricing→policies→products) reads coherently |

## 4. How it works

`scrape.py` loads the JSON, then calls `render.py` builders. Each builder is a small pure
function: data in → markdown string out. Example — the monthly-vs-annual doc computes savings
so the model doesn't have to:
```
Nimbus CRM Professional: $45/mo vs $36/mo annual → save $9/mo (20%)
```
`build_context.py` then reads the docs back in a fixed order and joins them into `context.md`.

Data flow: `catalog.json → render.* → docs/*.md → build_context → context.md`.
In the playground, the "Web scraping" card calls these endpoints and lets you click any doc to
preview its text — so you can *see* exactly what the agent will read.

## 5. How to test it

**In the playground** (the way you'll use it):
1. `make dev`, open the playground. Find **Phase 1 · Web scraping**.
2. Click **Scrape → docs** → pill shows "31 docs"; the doc list appears.
3. Click **Build context.md** → shows the context size.
4. Click a doc (e.g. `products/nimbus-crm.md`, or `monthly-vs-annual.md`) → preview its text.
5. Judge quality: does the product doc read cleanly? Is the annual = 20%-off math right?

**CLI shortcut:** `make scrape`
**Automated:** `make test` (Phase 1 = 5 tests: coverage, savings math, context concatenation, endpoints, path-traversal guard).

## 6. Key takeaways

- LLMs need **grounding**; both RAGless and RAG start from the *same clean corpus*.
- **Clean, well-structured source docs** are the highest-leverage thing you can do for answer quality.
- Pre-computing facts (savings %, pricing tables) beats asking the model to calculate.
- You can **inspect exactly what the agent will know** — no black box.

## 7. What's next

**Phase 2 — RAGless text chat:** feed `context.md` to an LLM and ask Nimbus a question in the
playground — the first phase where the agent actually *answers*.
