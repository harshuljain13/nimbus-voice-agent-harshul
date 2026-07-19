"""Split the scraped markdown docs into retrieval chunks (Phase 3, R5).

Each doc is split on markdown headings into sections; oversized sections are windowed with
overlap. Every chunk keeps its source doc + nearest heading so retrieval results (and the
Phase 4 visualization) can be labeled and the embedding carries topical context.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass

from ..scraping import paths

MAX_CHARS = 900   # a section longer than this is windowed
OVERLAP = 120     # chars of overlap between windows (keeps context across the cut)


@dataclass(frozen=True)
class Chunk:
    id: int
    doc: str
    heading: str
    text: str

    def as_dict(self) -> dict:
        return {"id": self.id, "doc": self.doc, "heading": self.heading, "text": self.text}

    def embed_text(self) -> str:
        """Text sent to the embedder — heading/doc prepended so the vector is topical."""
        return f"{self.doc} - {self.heading}\n{self.text}".strip()


def _sections(md: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, body) sections on '#'-prefixed lines."""
    sections: list[tuple[str, str]] = []
    heading, buf = "", []
    for line in md.splitlines():
        if line.lstrip().startswith("#"):
            if buf:
                sections.append((heading, "\n".join(buf).strip()))
                buf = []
            heading = line.lstrip("#").strip()
        else:
            buf.append(line)
    if buf:
        sections.append((heading, "\n".join(buf).strip()))
    return [(h, b) for h, b in sections if b]


def _window(text: str) -> list[str]:
    if len(text) <= MAX_CHARS:
        return [text]
    out, start = [], 0
    while start < len(text):
        end = min(start + MAX_CHARS, len(text))
        out.append(text[start:end])
        if end == len(text):
            break
        start = end - OVERLAP
    return out


def build_chunks(docs_dir: str | None = None) -> list[Chunk]:
    """Read docs/*.md + docs/products/*.md → a flat list of Chunks."""
    docs_dir = docs_dir or paths.DOCS_DIR
    files = sorted(glob.glob(os.path.join(docs_dir, "*.md")))
    files += sorted(glob.glob(os.path.join(docs_dir, "products", "*.md")))
    chunks: list[Chunk] = []
    cid = 0
    for f in files:
        doc = os.path.splitext(os.path.basename(f))[0]
        with open(f, encoding="utf-8") as fh:
            md = fh.read()
        for heading, body in _sections(md):
            for piece in _window(body):
                chunks.append(Chunk(cid, doc, heading or doc, piece))
                cid += 1
    return chunks
