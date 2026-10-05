# Three-minute demo

1. Start the local server and open `http://127.0.0.1:8766`.
2. Search **FST1 maize**. Open a returned 2008 paper excerpt and its cited
   page. Confirm the text is stored source text, not a generated claim.
3. Search **Sda1 sorbitol**, then **cercosporin light**. Compare the returned
   papers, pages, and retrieval trace.
4. Click an entity node and then a co-mention edge. Inspect its bounded
   evidence and PDF page link.
5. With the `AI answer` toggle on, search **What is known about Sda1 and
   sorbitol metabolism?** Show the generated answer with its `[n]` citations,
   then click one citation to open its source excerpt and PDF page. Turn the
   toggle off to return to source-excerpt mode.

Treat node and edge counts as navigation evidence only: co-mention is not
causality, and the dictionary graph is not comprehensive. If local semantic
indexing is unavailable, the demo remains usable in lexical mode. Generation
is not needed for source inspection and is never enabled implicitly.
