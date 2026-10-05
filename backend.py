#!/usr/bin/env python3
"""Local read-only HTTP facade for the prebuilt paper graph."""
from __future__ import annotations
import argparse, json, mimetypes, os, re, sqlite3
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

ROOT=Path(__file__).resolve().parent; SOURCE=ROOT/'data/source'; DB=ROOT/'data/graph.db'; STATIC=ROOT/'static'
def db():
    if not DB.exists(): raise RuntimeError('database unavailable')
    c=sqlite3.connect(f'file:{DB}?mode=ro',uri=True,timeout=5); c.row_factory=sqlite3.Row; return c
def counts(c):
    r=c.execute('SELECT (SELECT count(*) FROM papers) papers,(SELECT count(*) FROM pages) pages,(SELECT count(*) FROM chunks) chunks,(SELECT count(*) FROM entities WHERE id IN (SELECT entity_id FROM mentions)) entities,(SELECT count(DISTINCT source||"--"||target) FROM edges) edges').fetchone(); return dict(r)
def limit(v,default=20):
    if v is None: return default
    if isinstance(v,bool) or not isinstance(v,int) or not 1<=v<=20: raise ValueError('invalid limit')
    return v
def graph(c,focus=None,n=20,allowed=None,chunk_ids=None):
    params=[]; where=' HAVING mention_count>0'; join=''
    if chunk_ids is not None:
        if not chunk_ids:return {'nodes':[],'edges':[],'truncated':False}
        marks=','.join('?'*len(chunk_ids)); join=f' JOIN (SELECT id FROM chunks WHERE id IN ({marks})) selected ON selected.id=m.chunk_id'; params.extend(chunk_ids)
    if allowed is not None: where=' HAVING e.id IN ('+','.join('?'*len(allowed))+')'; params.extend(allowed)
    rows=c.execute('SELECT e.id,e.label,e.type,count(m.chunk_id) mention_count,count(DISTINCT k.paper_id) paper_count FROM entities e LEFT JOIN mentions m ON m.entity_id=e.id LEFT JOIN chunks k ON k.id=m.chunk_id'+join+' GROUP BY e.id'+where+' ORDER BY mention_count DESC LIMIT ?', params+[n]).fetchall()
    ids={r['id'] for r in rows}; edges=[]
    edgewhere=''; edgeparams=[]
    if chunk_ids is not None:
        edgewhere=' WHERE e.chunk_id IN ('+','.join('?'*len(chunk_ids))+')'; edgeparams=list(chunk_ids)
    for r in c.execute('SELECT source,target,type,count(DISTINCT paper_id) paper_count,count(*) evidence_count FROM edges e'+edgewhere+' GROUP BY source,target,type',edgeparams):
        if r['source'] in ids and r['target'] in ids: edges.append(dict(r,id=f"{r['source']}--{r['target']}--co_mention"))
    return {'nodes':[dict(r) for r in rows],'edges':edges[:100],'truncated':len(rows)>=n}
class Handler(BaseHTTPRequestHandler):
    def setup(self): super().setup(); self.request.settimeout(15)
    def reply(self,obj,code=200,typ='application/json'):
        b=obj if isinstance(obj,bytes) else json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Type',typ); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        p=urlparse(self.path); c=None
        try:
            if p.path.startswith('/api/'):
                try:c=db()
                except Exception:return self.reply({'error':'database unavailable'},503)
            if p.path=='/api/status':
                semantic={'ready':False,'ready_count':0,'total':0,'dimension':0,'warnings':['semantic status unavailable']}
                try:
                    import semantic_index; semantic=semantic_index.semantic_status(c)
                except Exception: pass
                import gateway
                gs=gateway.gateway_status(); gen_ok=bool(gs.get('available') and os.environ.get('LITELLM_MASTER_KEY'))
                warn=list(semantic.get('warnings',[]))
                if gen_ok: warn.append('Selected passages are sent to the configured model through LiteLLM/OpenRouter.')
                else: warn.append('AI-written answers unavailable ('+','.join(gs.get('warnings') or ['gateway_unavailable'])+'); source excerpts remain available.')
                self.reply(dict(ready=True,**counts(c),embedding_model=semantic.get('model'),generation_model=gs.get('generation_model'),answer_mode='extractive',generation_enabled=gen_ok,warnings=warn))
            elif p.path=='/api/papers': self.reply({'papers':[dict(r,pdf_url=f"/api/papers/{r['id']}/pdf") for r in c.execute('SELECT id,title,year,filename,pages FROM papers')]})
            elif p.path=='/api/graph':
                q=parse_qs(p.query); n=int(q.get('limit',[20])[0])
                if not 1<=n<=80: raise ValueError('invalid graph limit')
                focus=q.get('entity',[None])[0]; allowed=None
                if focus:
                    if not c.execute('SELECT 1 FROM entities WHERE id=?',(focus,)).fetchone(): return self.reply({'error':'entity not found'},404)
                    allowed={focus}; allowed.update(r[0] for r in c.execute('SELECT CASE WHEN source=? THEN target ELSE source END FROM edges WHERE source=? OR target=?',(focus,focus,focus)))
                self.reply(graph(c,focus,n,allowed))
            elif p.path.startswith('/api/entities/'):
                eid=unquote(p.path.rsplit('/',1)[1]); x=c.execute('SELECT * FROM entities WHERE id=?',(eid,)).fetchone()
                if not x:return self.reply({'error':'entity not found'},404)
                ev=[dict(r) for r in c.execute('SELECT k.id,k.paper_id,p.title paper_title,k.page,k.text FROM mentions m JOIN chunks k ON k.id=m.chunk_id JOIN papers p ON p.id=k.paper_id WHERE m.entity_id=?',(eid,))]
                for r in ev:r['pdf_url']=f"/api/papers/{r['paper_id']}/pdf#page={r['page']}"
                ns=[dict(r) for r in c.execute('SELECT e.id,e.label,e.type FROM entities e JOIN edges g ON e.id=CASE WHEN g.source=? THEN g.target ELSE g.source END WHERE g.source=? OR g.target=? GROUP BY e.id',(eid,eid,eid))]
                self.reply({'entity':dict(x, paper_count=len({r['paper_id'] for r in ev}),mention_count=len(ev)),'neighbors':ns,'evidence':ev[:100]})
            elif p.path.startswith('/api/edges/'):
                eid=unquote(p.path.rsplit('/',1)[1]); z=eid.split('--')
                if len(z)!=3:return self.reply({'error':'invalid edge id'},404)
                ev=[dict(r) for r in c.execute('SELECT k.id,k.paper_id,p.title paper_title,k.page,k.text FROM edges e JOIN chunks k ON k.id=e.chunk_id JOIN papers p ON p.id=k.paper_id WHERE e.source=? AND e.target=? AND e.type=?',(z[0],z[1],z[2]))]
                for r in ev:r['pdf_url']=f"/api/papers/{r['paper_id']}/pdf#page={r['page']}"
                if not ev:return self.reply({'error':'edge not found'},404)
                self.reply({'edge':{'id':eid,'source':z[0],'target':z[1],'type':z[2],'paper_count':len({r['paper_id'] for r in ev}),'evidence_count':len(ev)},'evidence':ev[:100]})
            elif p.path.startswith('/api/papers/') and p.path.endswith('/pdf'):
                r=c.execute('SELECT filename FROM papers WHERE id=?',(unquote(p.path.split('/')[3]),)).fetchone()
                if not r:return self.reply({'error':'paper not found'},404)
                self.reply((SOURCE/r['filename']).read_bytes(),typ='application/pdf')
            else:
                rel=unquote(p.path.lstrip('/') or 'index.html'); target=(STATIC/rel).resolve()
                if STATIC.resolve() not in target.parents or not target.is_file():return self.reply({'error':'not found'},404)
                self.reply(target.read_bytes(),typ=mimetypes.guess_type(str(target))[0] or 'application/octet-stream')
        except (ValueError,sqlite3.Error,TimeoutError): self.reply({'error':'bad request'},400)
        finally:
            if c:c.close()
    def do_POST(self):
        if urlparse(self.path).path!='/api/search':return self.reply({'error':'not found'},404)
        try:
            n=int(self.headers.get('Content-Length','-1'))
            if n<0:return self.reply({'error':'Content-Length required'},411)
            if n>65536:return self.reply({'error':'body too large'},413)
            b=json.loads(self.rfile.read(n))
            if not isinstance(b,dict) or not isinstance(b.get('query'),str) or len(b['query'])>4000 or (b.get('entity_id') is not None and not isinstance(b['entity_id'],str)):raise ValueError('bad body')
            lim=limit(b.get('limit',8)); c=db()
            from retrieval import retrieve
            packet=retrieve(c,b['query'].strip(),lim,b.get('entity_id'),True)
            ids={e['id'] for r in packet['results'] for e in r.get('entities',[])}
            answer={'answer':'No matching source passages were found.','answer_mode':'extractive','generation_model':None,'warnings':packet['warnings']}
            if packet['results']:
                answer['answer']='Source excerpts: '+' '.join(f'[{i}]' for i in range(1,len(packet['results'])+1))
            if b.get('generate',True) is True:
                import gateway; answer=gateway.generate_answer(b['query'],packet['results'])
            result_ids=[r['id'] for r in packet['results']]
            self.reply({'query':b['query'].strip(),**answer,'results':packet['results'],'graph':graph(c,b.get('entity_id'),80,ids,result_ids),'trace':packet['trace']})
        except (ValueError,json.JSONDecodeError):self.reply({'error':'bad JSON or invalid request'},400)
        except Exception:self.reply({'error':'database unavailable'},503)
        finally:
            if 'c' in locals():c.close()
    def log_message(self,*args):pass
if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('command',choices=['serve']); ap.add_argument('--host',default='127.0.0.1'); ap.add_argument('--port',type=int,default=8766); a=ap.parse_args(); ThreadingHTTPServer((a.host,a.port),Handler).serve_forever()
