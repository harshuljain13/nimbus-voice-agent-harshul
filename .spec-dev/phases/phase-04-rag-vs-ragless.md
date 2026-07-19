# Phase 4 — RAG vs RAGless + Reranking + 2D Visualization (Report / Design Doc)

> Status: ✅ Done · Requirements: R3 + R5 (rerank/viz) · Tests: 6 passing · Playground: compare + rerank + vector map
> Design target: [`../reference.md`](../reference.md).

## 1. Concept — what this phase teaches

Phase 3 made RAG *work*. Phase 4 makes it **comparable, better, and visible**:

- **Compare** RAG vs RAGless side by side — so you *see* the trade (tokens vs latency), not guess it.
- **Reranking** — vector search is fast but approximate; a second, smarter pass reorders the
  top candidates so the *best* chunks land in the prompt.
- **Visualization** — embeddings are just points in space. Projecting them to 2D and drawing the
  query + its nearest chunks turns "semantic search" from an abstraction into something you watch.

The headline question you asked — *"shouldn't RAG be lower latency?"* — is answered by the compare
view: RAG's LLM call *is* faster on a small prompt, but the query-embed round-trip (+ OpenAI
caching the big RAGless prompt) makes totals similar. **RAG's guaranteed win is tokens/cost/scale.**

## 2. What we built

```
backend/app/rag/
  viz_math.py   numpy-only PCA (fit once) + KMeans (cluster colors) — no scikit-learn
  rerank.py     light = LLM rerank (gpt-4o-mini orders candidates); rich = cross-encoder. Graceful fallback.
  index.py      + 2D projection at build (projection.json): points{x,y,cluster} + cluster labels + PCA
  service.py    + do_rerank (fetch a bigger pool, rerank to k, rerank_ms) + query_with_viz (query point)
```
Endpoints: `GET /rag/visualization` (the scatter), `POST /rag/query` (retrieve + project the query),
`rerank` flag on `/chat` + `/rag/retrieve`.

Frontend:
- **`rag.html`** — the vector map: 265 chunk points (PCA→2D, KMeans-colored), the query as a white
  diamond with connectors to the ranked nearest chunks, a k box, a rerank toggle, live latency
  breakdown, retrieved-chunk list, hover-to-read, and rebuild.
- **Playground**: a **rerank** toggle + **Vector map ↗** link in the RAG options, a
  **⚖ Compare RAG vs RAGless** button → a table of context/prompt tokens + RAG/LLM/total ms, and a
  **Sources: doc · doc** citation line under each RAG answer (from the retrieved chunks — ground
  truth, not model-generated; RAG mode only).

## 3. Design decisions

| Decision | Choice | Why |
|---|---|---|
| Compare | run the same question through RAG and RAGless, show tokens + per-stage ms | Directly answers "which is faster/cheaper?" with real numbers, not intuition. |
| Rerank (light) | LLM rerank: fetch `max(k·3, 12)` candidates, ask gpt-4o-mini to order, keep k | No extra model/deps; better ordering than raw cosine. Costs an LLM call (~900ms) — shown as `rerank_ms`. |
| Rerank safety | any failure → fall back to vector order | Rerank is best-effort; a bad JSON reply must never break a turn. |
| Dimensionality reduction | **PCA** (numpy SVD), fit once at build, reused to project queries | Deterministic, dependency-free, and queries land in the *same* space as chunks. |
| Clustering | KMeans (numpy), labeled by the most common catalog topic per cluster | Turns anonymous blobs into a readable legend (Pricing, FAQ, Finance…). |
| Viz transport | precompute `projection.json` at build; `/rag/query` only projects the 1 query vector | The 265-point scatter is static; only the query moves — cheap per query. |

## 4. How it works

Build now also writes `projection.json`: PCA(mean, 2 components) + each chunk's (x, y, cluster).
Per viz query: embed → FAISS top-k → project the query with the *same* PCA → return the query
point + retrieved ids; the canvas highlights them and draws ranked connectors. Rerank (when on)
fetches a larger candidate pool and reorders it before the final k.

## 5. How to test it

**In the playground:**
1. **Knowledge source → RAG**, then click **⚖ Compare RAG vs RAGless** → a table: context tokens
   (~500 vs 23.5k), prompt tokens, RAG ms, LLM ms, total ms. Read the note on why totals are close.
2. Toggle **Rerank retrieved chunks** and re-ask → answer quality can improve; `rerank_ms` appears.
3. Click **Vector map ↗** → the visualization page.

**On the vector map (`rag.html`):**
4. Type *"how do refunds work?"* → **Run query** → the white **query diamond** connects to the
   nearest chunks (numbered by rank); the right panel lists them with scores + latency breakdown.
5. Tick **rerank** + raise **k** → different retrieval; watch `rerank_ms`.
6. **Hover** any point → read that chunk; the **legend** names the 8 clusters.

**Automated:** `make test` (Phase 4 = 6 tests; embeddings + LLM + rerank mocked, offline).
**Live-verified:** 265-point projection, 8 labeled clusters, query projection, rerank reorders (~900ms).

## 6. Key takeaways

- **Compare, don't assume:** RAG ≈ RAGless on wall-clock here, but 98% cheaper in tokens — the
  compare view makes the real trade legible.
- **Rerank buys quality for latency:** a smarter second pass, opt-in and timed.
- **PCA makes embeddings tangible:** the same 2D space holds chunks *and* the query, so retrieval
  is something you can literally see.

## 7. What's next

**Phase 5 — LLM controls:** add **Gemini** (flash/pro) as a second provider, **conversation
history** (last-N verbatim + a rolling summary of older turns), and explicit **RAG-routing** rules
in the system prompt (catalog facts → RAG; cart math/actions → tools, no RAG).
