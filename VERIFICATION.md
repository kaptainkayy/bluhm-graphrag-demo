# Verification snapshot

Date: **September 28, 2026**. This records the current local snapshot, not a
promise that a future database is unchanged.

- Source verification reported 27 matching PDF SHA-256 records; the source
  set contains 27 PDFs plus `INDEX.md`.
- Database counts are 27 papers, 384 pages, 1,424 chunks, 28 active entity
  nodes, and 132 aggregated graph edges. The database also contains 751 raw
  co-mention support records before the entity set was extended (895 after).
  Entity set extended 28 September 2026 with six organisms (Arabidopsis,
  Cercospora zeina, Dothideomycetes, Solanum lycopersicoides, Fusarium
  virguliforme, Bipolaris cookei); mentions and co-mention edges were rebuilt
  from chunk text with a database backup taken first.
- Embeddings are the local `nomic` 768-dimensional snapshot. No model
  download was performed.
- HTTP verification ran `python3 -m unittest discover -s tests -v`: **13 tests
  passed** in the current verification record.
- The live service is loopback-only on port 8766. Confirm its current PID and
  command line before stopping it; do not rely on a copied PID.
- Live Playwright checks passed at desktop and mobile sizes: graph overview,
  FST1 neighborhood, edge evidence, search, PDF page links, all 27 corpus
  entries, filters/reset, error handling, and no horizontal overflow or
  browser console errors. Command: `node /tmp/opencode/bluhm-ui-qa.cjs`.
- Independent screenshot review passed after graph-label spacing, visible PDF
  controls, and the mobile header were corrected. Screenshots are in
  `/tmp/opencode/bluhm-demo-{desktop,selected,mobile}.png`.
- Independent technical review passed the graph-provenance checks: graph
  paths use same-chunk evidence, and search-result graph edges are supported
  by the returned chunks. These checks do not establish biological causality.
- Nine sampled FST1, Sda1, and CFP excerpts matched text extracted directly
  from their cited physical PDF pages. All 27 PDF page counts matched.

Known limits: paper refresh is not automated, the graph is dictionary-based
and co-mention-only, semantic mode has a lexical fallback. AI-written answers
run through `deepseek/deepseek-v4.1-flash` on the local LiteLLM gateway after
the user replaced the OpenRouter credential and recreated the container
(28 September 2026). Live checks: `/api/status` reports `generation_enabled:
true`; `FST1 fumonisin` and `Sda1 sorbitol` questions returned
`answer_mode: generated` with citations validated against the returned
excerpts; a live browser run showed the `AI-generated answer · verify sources`
badge with working citation links and zero console errors
(`/tmp/opencode/bluhm-demo-generated.png`). Invalid, empty, or truncated
generations fall back to labeled source excerpts (observed during tuning;
`human_review_needed` warnings are always attached). Generated answers are
model output, not verified biology.
