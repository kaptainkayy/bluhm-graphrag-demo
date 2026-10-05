import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
import retrieval


def database():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
      CREATE TABLE papers(id TEXT PRIMARY KEY,title TEXT,year INT);
      CREATE TABLE chunks(id TEXT PRIMARY KEY,paper_id TEXT,page INT,text TEXT);
      CREATE VIRTUAL TABLE chunks_fts USING fts5(id, text);
      CREATE TABLE entities(id TEXT PRIMARY KEY,label TEXT,type TEXT);
      CREATE TABLE mentions(chunk_id TEXT,entity_id TEXT);
      CREATE TABLE edges(id TEXT,source TEXT,target TEXT,type TEXT,paper_id TEXT,chunk_id TEXT);
      INSERT INTO papers VALUES('p','Paper title',2020);
      INSERT INTO chunks VALUES('c1','p',7,'FST1 and FUG1 control fumonisin biosynthesis.');
      INSERT INTO chunks VALUES('c2','p',8,'FUG1 controls a related pathway.');
      INSERT INTO chunks VALUES('c3','p',9,'FST1 and FUG1 are discussed together.');
      INSERT INTO chunks_fts(id,text) SELECT id,text FROM chunks WHERE id <> 'c3';
      INSERT INTO entities VALUES('e1','FST1','gene');
      INSERT INTO entities VALUES('e2','FUG1','gene');
      INSERT INTO mentions VALUES('c1','e1');
      INSERT INTO mentions VALUES('c1','e2');
      INSERT INTO mentions VALUES('c2','e2');
      INSERT INTO mentions VALUES('c3','e1');
      INSERT INTO mentions VALUES('c3','e2');
      INSERT INTO edges VALUES('x','e1','e2','co-mention','p','c1');
    """)
    return c


class RetrievalTests(unittest.TestCase):
    def test_exact_anchor_and_stable_excerpt(self):
        result = retrieval.retrieve(database(), "FST1 fumonisin", use_graph=False)
        self.assertEqual(result["results"][0]["id"], "c1")
        self.assertEqual(result["results"][0]["text"], "FST1 and FUG1 control fumonisin biosynthesis.")
        self.assertTrue(result["results"][0]["pdf_url"].endswith("/pdf#page=7"))
        self.assertNotIn("c2", [x["id"] for x in result["results"]])

    def test_graph_provenance_and_toggle(self):
        with patch("semantic_index.semantic_search", return_value=[]):
            on = retrieval.retrieve(database(), "FST1", use_graph=True)
            off = retrieval.retrieve(database(), "FST1", use_graph=False)
        self.assertIn("c3", on["trace"]["graph_added_ids"])
        self.assertTrue(on["trace"]["graph_paths"])
        for path in on["trace"]["graph_paths"]:
            if path["chunk_id"] == "c3":
                self.assertEqual({"e1", "e2"}, {e["id"] for e in retrieval._chunk_entities(database(), "c3")})
        self.assertEqual(off["trace"]["graph_added_ids"], [])

    def test_empty_stopword_and_unknown_symbol(self):
        for query in ("", "what does the literature say about", "FST999"):
            with self.subTest(query=query):
                self.assertEqual(retrieval.retrieve(database(), query)["results"], [])

    def test_entity_filter(self):
        result = retrieval.retrieve(database(), "fumonisin", entity_id="e1", use_graph=False)
        self.assertTrue(result["results"])
        self.assertTrue(all(any(e["id"] == "e1" for e in r["entities"]) for r in result["results"]))


if __name__ == "__main__":
    unittest.main()
