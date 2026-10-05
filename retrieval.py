"""Bounded, extractive retrieval over the local paper graph.

This module deliberately owns no database writes and makes no network or model
calls.  The semantic function is imported lazily so applications and tests can
replace it with their local vector index.
"""
from __future__ import annotations

import re
from collections import defaultdict

STOP = {"a", "an", "and", "are", "for", "from", "how", "in", "is", "of",
        "on", "or", "the", "to", "what", "which", "with", "does", "do",
        "tell", "about", "show", "me", "please", "does"}
TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")


def _tokens(q):
    return [x for x in TOKEN.findall(q) if x.lower() not in STOP and len(x) > 1]


def _fts(conn, q, limit=40):
    words = _tokens(q)
    if not words:
        return []
    expr = " AND ".join('"' + w.replace('"', '""') + '"' for w in words)
    try:
        return conn.execute("SELECT id, bm25(chunks_fts) AS rank FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?", (expr, limit)).fetchall()
    except Exception:
        return []


def _entities(conn, q):
    found = []
    for r in conn.execute("SELECT id,label,type FROM entities"):
        label = str(r[1] or "")
        if label and re.search(r"(?<![A-Za-z0-9])" + re.escape(label) + r"(?![A-Za-z0-9])", q, re.I):
            found.append({"id": r[0], "label": label, "type": r[2]})
    return found


def _chunk(conn, cid):
    return conn.execute("""SELECT c.id,c.paper_id,c.page,c.text,p.title
                          FROM chunks c LEFT JOIN papers p ON p.id=c.paper_id
                          WHERE c.id=?""", (cid,)).fetchone()


def _chunk_entities(conn, cid):
    return [dict(r) for r in conn.execute("""SELECT e.id,e.label,e.type FROM mentions m
        JOIN entities e ON e.id=m.entity_id WHERE m.chunk_id=? ORDER BY e.id""", (cid,))]


def _reasons(labels, direct=False, graph=None):
    out = (["direct lexical match"] if direct else [])
    if graph:
        out.append("related co-mention evidence: " + " ↔ ".join(graph))
    return out or ["semantic similarity"]


def retrieve(conn, query, limit=8, entity_id=None, use_graph=True):
    """Return stable page excerpts and bounded graph evidence for *query*."""
    empty = {"results": [], "warnings": [], "trace": {"seed_entities": [], "lexical_candidates": 0,
             "semantic_candidates": 0, "graph_candidates": 0, "graph_added_ids": [], "graph_paths": []}}
    if not isinstance(query, str) or not _tokens(query):
        return empty
    lex = _fts(conn, query)
    lex_ids = [r[0] for r in lex]
    known = _entities(conn, query)
    if entity_id is not None:
        known = [e for e in known if str(e["id"]) == str(entity_id)]
    # Gene-like unknown anchors must not fall through to an unrelated vector hit.
    gene_words = [w for w in _tokens(query) if re.fullmatch(r"[A-Z][A-Za-z0-9_-]{1,}", w)]
    known_gene = {e["label"].lower() for e in known if str(e.get("type", "")).lower() == "gene"}
    unknown_gene = bool(gene_words) and not any(w.lower() in known_gene for w in gene_words)
    sem = []
    if not unknown_gene and (lex_ids or known):
        try:
            from semantic_index import semantic_search
            sem = semantic_search(conn, query, limit=40) or []
        except Exception:
            empty["warnings"].append("Semantic search unavailable; using lexical and graph retrieval.")
            sem = []
    sem = [(cid, float(score)) for cid, score in sem if float(score) >= .5]
    empty["trace"]["lexical_candidates"] = len(lex_ids)
    empty["trace"]["semantic_candidates"] = len(sem)
    empty["trace"]["seed_entities"] = [e["id"] for e in known]
    direct = set(lex_ids)
    scores = defaultdict(float)
    for rank, cid in enumerate(lex_ids): scores[cid] += 1 / (60 + rank + 1)
    for rank, (cid, _) in enumerate(sem): scores[cid] += 1 / (60 + rank + 1)
    # An explicit entity anchor is stronger than a merely similar passage.
    for entity in known:
        for row in conn.execute("SELECT chunk_id FROM mentions WHERE entity_id=?", (entity["id"],)):
            if row[0] in scores:
                scores[row[0]] += .05
    hybrid_ids = set(scores)
    graph_ids, paths = [], []
    seeds = [e["id"] for e in known]
    if use_graph and seeds:
        placeholders = ",".join("?" * len(seeds))
        rows = conn.execute(f"""SELECT DISTINCT m2.chunk_id,e1.label,e2.label FROM mentions m1
          JOIN mentions m2 ON m2.chunk_id=m1.chunk_id AND m2.entity_id<>m1.entity_id
          JOIN entities e1 ON e1.id=m1.entity_id JOIN entities e2 ON e2.id=m2.entity_id
          WHERE m1.entity_id IN ({placeholders}) LIMIT 20""", seeds).fetchall()
        for cid, a, b in rows:
            if cid not in hybrid_ids and cid not in graph_ids:
                graph_ids.append(cid); paths.append({"chunk_id": cid, "entities": [a, b]})
                scores[cid] += .25 / 60
            elif cid in hybrid_ids:
                paths.append({"chunk_id": cid, "entities": [a, b], "supported": True})
        empty["trace"]["graph_added_ids"] = graph_ids
        empty["trace"]["graph_paths"] = paths
    empty["trace"]["graph_candidates"] = len(graph_ids)
    allowed = set(scores)
    rows = []
    for cid in sorted(allowed, key=lambda x: scores[x], reverse=True):
        r = _chunk(conn, cid)
        if not r: continue
        ents = _chunk_entities(conn, cid)
        if entity_id is not None and not any(str(e["id"]) == str(entity_id) for e in ents): continue
        if known_gene and not any(str(e["label"]).lower() in known_gene for e in ents): continue
        graph = next((p["entities"] for p in paths if p["chunk_id"] == cid), None)
        rows.append({"id": r[0], "paper_id": r[1], "paper_title": r[4], "page": r[2], "text": r[3],
                     "pdf_url": f"/api/papers/{r[1]}/pdf#page={r[2]}", "score": scores[cid],
                     "entities": ents, "retrieval_reasons": _reasons([e["label"] for e in ents], cid in direct, graph)})
    return {"results": rows[:max(0, limit)], "warnings": empty["warnings"], "trace": empty["trace"]}
