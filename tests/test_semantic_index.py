import sqlite3, unittest
from unittest.mock import patch
import sys
from pathlib import Path
sys.path.insert(0, Path(__file__).parents[1].as_posix())
import semantic_index as s
class SemanticTests(unittest.TestCase):
 def test_cosine(self):
  c=sqlite3.connect(':memory:'); c.row_factory=sqlite3.Row
  c.execute('create table embeddings(chunk_id text,model text,dim int,vector text,model_digest text)'); c.execute('create table model_metadata(model text,digest text)'); c.execute('insert into model_metadata values(?,?)',(s.MODEL,'d'))
  c.executemany('insert into embeddings values(?,?,?,?,?)',[('a',s.MODEL,2,'[1,0]','d'),('b',s.MODEL,2,'[0,1]','d')])
  with patch.object(s,'embed_query',return_value=[1,0]): self.assertEqual(s.semantic_search(c,'x'),[('a',1.0),('b',0.0)])
 def test_bad_vector(self):
  with patch.object(s,'_post',return_value={'embeddings':[[float('nan')]]}):
   with self.assertRaises(RuntimeError): s.embed_query('x')
if __name__=='__main__': unittest.main()
