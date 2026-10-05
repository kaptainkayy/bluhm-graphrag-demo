# Bluhm local graph-assisted RAG demo

This is a local operator demo on Zephyrus. The prebuilt SQLite snapshot is
served read-only at `http://127.0.0.1:8766`; no source files or database are
uploaded to a hosted service.

## Run

From this directory:

```bash
python3 backend.py serve --port 8766
```

Open `http://127.0.0.1:8766`. To check or stop a service, inspect the process
and port first; stop only the service you started. A foreground service stops
with Ctrl-C. Never kill an unknown process. For an SSH session, use the real
Zephyrus SSH host in this placeholder command:

```bash
ssh -N -L 8766:127.0.0.1:8766 <Zephyrus-SSH-host>
```

The snapshot contains 27 PDFs and `INDEX.md` copied from
`kayai3:/home/kayai3/Documents/Burt Blums Research`, with 384 pages and 1,424
chunks. The persistent database is `data/graph.db`. There is currently no
paper-ingestion command: refresh is not automated. `semantic_index.py index`
refreshes vectors only; it does not ingest papers.

The service uses Python's standard library, SQLite FTS5, and the original
`pdftotext` extraction. Retrieval combines lexical, available semantic, and
graph traces. If the local embedding service is unavailable it falls back to
lexical retrieval. AI-written answers are enabled by default through the
approved `deepseek/deepseek-v4.1-flash` route on the local LiteLLM gateway
(OpenRouter upstream): only the question and the selected excerpts are sent,
answers must cite the returned excerpts `[1]..[N]`, and any invalid, empty, or
truncated generation falls back to labeled source excerpts. The UI toggle
`AI answer` turns generation off for source-only mode. Human review of
generated answers is still required. No model downloads were performed.

Graph links are curated dictionary same-chunk co-mentions, not biological
proof and not a comprehensive extraction. Selected excerpts use the approved
generation route only when explicitly enabled.

See [DEMO.md](DEMO.md) for a short walkthrough and [VERIFICATION.md](VERIFICATION.md)
for the current evidence and limits.
