#!/usr/bin/env python3
"""Local Ollama semantic indexing; deliberately has no model download path."""
from __future__ import annotations
import argparse, json, math, sqlite3, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

MODEL = "nomic-embed-text:latest"
OLLAMA = "http://127.0.0.1:11434"
PREFIX_DOC, PREFIX_QUERY = "search_document: ", "search_query: "

def _post(path, payload, timeout=45):
    data=json.dumps(payload).encode(); last=None
    for attempt in range(2):
        try:
            with urlopen(Request(OLLAMA+path, data=data, headers={"Content-Type":"application/json"}), timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:
            last=e
            if attempt: raise RuntimeError(f"Ollama request failed: {e}") from e
    raise RuntimeError(str(last))

def _tags():
    try:
        with urlopen(OLLAMA+"/api/tags", timeout=30) as r: return json.loads(r.read())
    except Exception as e: raise RuntimeError(f"Ollama tags request failed: {e}") from e

def _metadata(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS model_metadata (model TEXT PRIMARY KEY, digest TEXT, metadata TEXT NOT NULL, updated REAL NOT NULL)")
    tags=_tags()
    item=next((x for x in tags.get("models",[]) if x.get("name")==MODEL), None)
    if not item: raise RuntimeError(f"required local model unavailable: {MODEL}")
    digest=item.get("digest", "")
    conn.execute("INSERT OR REPLACE INTO model_metadata VALUES(?,?,?,?)", (MODEL,digest,json.dumps(item,sort_keys=True),time.time()))
    try: conn.execute("ALTER TABLE embeddings ADD COLUMN model_digest TEXT")
    except sqlite3.OperationalError: pass
    conn.commit(); return digest

def _vectors(items):
    out=_post("/api/embed", {"model":MODEL,"input":items})
    vs=out.get("embeddings")
    if not isinstance(vs,list) or len(vs)!=len(items): raise RuntimeError("Ollama returned invalid embedding batch")
    dim=None
    for v in vs:
        if not isinstance(v,list) or not v: raise RuntimeError("invalid embedding vector")
        if dim is None: dim=len(v)
        if len(v)!=dim or any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in v): raise RuntimeError("invalid embedding vector values")
    return [[float(x) for x in v] for v in vs]

def embed_query(query):
    return _vectors([PREFIX_QUERY+query])[0]

def index_database(db_path, batch_size=10):
    conn=sqlite3.connect(str(db_path)); conn.row_factory=sqlite3.Row
    digest=_metadata(conn); total=conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
    rows=conn.execute("SELECT id,text FROM chunks ORDER BY rowid").fetchall(); done=0; started=time.perf_counter(); dim=None
    for pos in range(0,len(rows),batch_size):
        batch=rows[pos:pos+batch_size]
        sql="SELECT chunk_id FROM embeddings WHERE model=? AND model_digest=? AND chunk_id IN (%s)" % ','.join('?'*len(batch))
        cached=set()
        for cr in conn.execute("SELECT chunk_id,dim,vector FROM embeddings WHERE model=? AND model_digest=? AND chunk_id IN (%s)"%','.join('?'*len(batch)),[MODEL,digest]+[r['id'] for r in batch]):
            try:
                v=json.loads(cr['vector']); valid=bool(v) and cr['dim']==len(v) and all(isinstance(x,(int,float)) and math.isfinite(x) for x in v)
            except Exception: valid=False
            if valid: cached.add(cr['chunk_id'])
        need=[r for r in batch if r['id'] not in cached]
        if need:
            vectors=_vectors([PREFIX_DOC+r['text'] for r in need]); dim=dim or len(vectors[0])
            for r,v in zip(need,vectors): conn.execute("INSERT OR REPLACE INTO embeddings(chunk_id,model,dim,vector,created,model_digest) VALUES(?,?,?,?,?,?)",(r['id'],MODEL,len(v),json.dumps(v,separators=(',',':')),time.time(),digest))
            conn.commit()
        done += len(batch)
    elapsed=time.perf_counter()-started; conn.close()
    return {"model":MODEL,"digest":digest,"total_chunks":total,"indexed":done,"dimension":dim or 0,"batch_size":batch_size,"elapsed_seconds":elapsed,"throughput_chunks_per_second":done/elapsed if elapsed else 0,"device":"ollama-local (CPU/GPU determined by Ollama)"}

def semantic_search(conn, query, limit=40):
    q=embed_query(query); qn=math.sqrt(sum(x*x for x in q)); out=[]
    try: digest=conn.execute("SELECT digest FROM model_metadata WHERE model=?",(MODEL,)).fetchone()[0]
    except Exception: raise RuntimeError("active embedding metadata unavailable")
    for r in conn.execute("SELECT chunk_id,dim,vector FROM embeddings WHERE model=? AND model_digest=?",(MODEL,digest)):
        try: v=json.loads(r['vector']); n=math.sqrt(sum(float(x)*float(x) for x in v)); sim=sum(a*b for a,b in zip(q,v))/(qn*n)
        except Exception: continue
        if r['dim']==len(q)==len(v) and n and qn and all(math.isfinite(float(x)) for x in v) and math.isfinite(sim): out.append((r['chunk_id'],sim))
    return sorted(out,key=lambda x:x[1],reverse=True)[:limit]

def semantic_status(conn):
    try: meta=conn.execute("SELECT digest FROM model_metadata WHERE model=?",(MODEL,)).fetchone()
    except sqlite3.OperationalError: meta=None
    total=conn.execute("SELECT count(*) FROM chunks").fetchone()[0]; digest=meta[0] if meta else None
    ready=conn.execute("SELECT count(*) FROM embeddings WHERE model=? AND model_digest=?",(MODEL,digest)).fetchone()[0] if digest else 0
    dims=[r[0] for r in conn.execute("SELECT DISTINCT dim FROM embeddings WHERE model=?",(MODEL,))]; warnings=[]
    if len(dims)>1: warnings.append("mixed dimensions")
    complete=ready==total and total>0
    if not complete: warnings.append("index incomplete")
    return {"model":MODEL,"ready":complete,"ready_count":ready,"total":total,"dimension":dims[0] if len(dims)==1 else 0,"warnings":warnings}

if __name__ == '__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('command',choices=['index','status']); ap.add_argument('--db',default=str(Path(__file__).parent/'data/graph.db')); a=ap.parse_args()
    c=sqlite3.connect(a.db)
    result=index_database(a.db) if a.command=='index' else semantic_status(c); print(json.dumps(result,indent=2))
    if a.command=='index': Path(__file__).parent.joinpath('generateddata').mkdir(exist_ok=True); Path(__file__).parent.joinpath('generateddata/embedding-report.json').write_text(json.dumps(result,indent=2)+'\n')
