# Phase 3 — RAG Retrieval (Report / Design Doc)

> Status: ✅ Done · Requirement: R5 (retrieval half) · Tests: 5 passing · Playground: RAG option live
> Design target: [`../reference.md`](../reference.md). Rerank + 2D vector viz are Phase 4.

## 1. Concept — what this phase teaches

Phase 2 (RAGless) proved grounding works but paid **23,482 tokens every turn** by dumping the
whole catalog into the prompt. That doesn't scale. **RAG (Retrieval-Augmented Generation)** fixes
it: store the docs as many small **chunks**, turn each into a **vector** (embedding), and at
question time fetch only the **top-k** chunks whose vectors are closest to the question's vector.
Inject *those* few hundred tokens instead of the whole corpus.

The core idea is **semantic search**: an embedding maps text to a point in space where similar
*meaning* → nearby points. "What's your refund policy?" lands near the refund chunk even without
sharing exact words. Cosine similarity ranks them.

Live result on the same refund question: **23,482 → 490 tokens (98% smaller)**, and the top hit
was `refund / Refund Policy` (score 0.58). Answer stayed correct.

## 2. What we built

```
backend/app/rag/
  chunk.py     docs/*.md → Chunk(id, doc, heading, text); split on headings, window big sections
  embed.py     light profile: OpenAI text-embedding-3-small (1536-d); L2-normalized (cosine)
  index.py     FAISS IndexFlatIP over the vectors; build / load / status / search(top-k)
  service.py   query(text, k): embed → search → context string + latency (embed_ms, search_ms)
backend/data/rag/   faiss.index, embeddings.npy, chunks.json  (generated, git-ignored)
```
Endpoints: `GET /rag/status`, `POST /rag/build`, `POST /rag/retrieve {query,k}`; and `/chat` now
honors `use_rag` + `top_k`. Orchestrator: when `use_rag`, retrieve top-k, inject the chunks as
the grounding block, record `rag_ms`, and return the retrieved chunks in `meta.rag`.

Playground: **RAG** un-locked in *Knowledge source* + a **top-k slider** + an index-status line;
the "This turn" panel shows the **rag_ms** stage and the **retrieved chunks with scores**.

## 3. Design decisions

| Decision | Choice | Why |
|---|---|---|
| Chunking | split on markdown headings; window sections >900 chars (120 overlap) | Headings are natural semantic boundaries; overlap avoids cutting a fact in half. 31 docs → **265 chunks**. |
| Embed text | prepend `doc - heading` to each chunk | The vector carries topical context, so "pricing" chunks cluster with pricing. |
| Embedding model | `light` = OpenAI `text-embedding-3-small` (1536-d) | Uses the key we have, no `torch`, Railway-friendly. `rich` (local MiniLM) is opt-in for Phase 4 viz. |
| Similarity | L2-normalize vectors + FAISS **IndexFlatIP** | Inner product on unit vectors == cosine; `IndexFlatIP` is exact (no recall loss at this scale). |
| Where injected | retrieved chunks replace `context.md` in the same grounding block | Reuses the Phase 2 prompt; the LLM path doesn't care whether context came from RAG or RAGless. |
| Build trigger | auto-build on first RAG query (also `POST /rag/build`) | Zero-setup; the first RAG turn is slightly slower (shown). |

## 4. How it works

Build (once): `chunk docs → embed all 265 → FAISS index + chunks.json`.
Per RAG turn:
```
/chat {use_rag:true, top_k:4}
  → embed the question           # embed_ms
  → FAISS top-k search           # search_ms   (rag_ms = embed + search)
  → join k chunks → grounding block → LLM → answer
  → meta.rag = {k, chunks:[{doc,heading,score}]}
```
The prompt is now ~490 tokens instead of 23.5k.

**Latency nuance worth knowing:** RAG isn't always *faster* end-to-end. The query embedding adds
~300-640 ms, and OpenAI answers a 23k-token prompt almost as fast as a 490-token one (plus prompt
caching). RAG's guaranteed win is **cost + scale** (98% fewer prompt tokens, and it works when the
corpus is far bigger than a context window) — latency depends. The dashboard makes this visible.

## 5. How to test it

**In the playground:**
1. `make dev`, open the playground. Set **Knowledge source → RAG** (a top-k slider + `index: 265
   chunks` appear).
2. Ask *"What's the refund policy?"* → grounded answer; the "This turn" panel shows **rag_ms**, a
   tiny **context-token** count (~500 vs 23.5k), and the **retrieved chunks with scores**.
3. Move **Top-k** 1 → 8 and re-ask → more/fewer chunks retrieved.
4. Ask *"How much is Nimbus CRM Professional?"* → **$45/mo ($36 annual)**; top chunks are pricing/CRM.
5. Flip **RAGless ↔ RAG** on the same question → compare context tokens (23.5k vs ~500) and answers.
6. **Inspect context** in RAG mode → the prompt now contains only the retrieved chunks.

**Automated:** `make test` (Phase 3 = 5 tests; embeddings + LLM mocked, offline).
**Live-verified:** 265-chunk index; refund query → 490 tokens (98% smaller), correct top chunk + answer.

## 6. Key takeaways

- **Embeddings = semantic search:** similar meaning → nearby vectors; cosine ranks them.
- **RAG trades a big static prompt for a small dynamic one** — 98% fewer prompt tokens here.
- **RAG's core win is cost + scale, not always latency** — measure, don't assume.
- The LLM path is grounding-source-agnostic: RAG vs RAGless is just *what fills the context block*.

## 7. What's next

**Phase 4 — RAG vs RAGless + visualization:** a proper RAG↔RAGless toggle with latencies side by
side, **reranking** the retrieved pool, and a **2D vector-cluster map** (PCA) with the query point
+ nearest chunks overlaid — so you can *see* retrieval happen.
