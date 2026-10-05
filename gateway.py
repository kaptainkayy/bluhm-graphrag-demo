"""Small source-grounded gateway client; credentials remain in the environment."""
import json, os, re, time, urllib.request, urllib.error

BASE=os.environ.get('LITELLM_GATEWAY_BASE','http://127.0.0.1:8787/v1')
DEFAULT_MODEL='deepseek/deepseek-v4.1-flash'
def _configured(): return os.environ.get('LITELLM_GATEWAY_MODEL') or DEFAULT_MODEL
def _call(path,payload=None,timeout=60):
    key=os.environ.get('LITELLM_MASTER_KEY')
    if not key: raise RuntimeError('missing_credentials')
    req=urllib.request.Request(BASE+path,data=None if payload is None else json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='GET' if payload is None else 'POST')
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:return r.status,json.loads(r.read())
    except urllib.error.HTTPError as e: raise RuntimeError(f'http_{e.code}') from None
    except Exception as e: raise RuntimeError(type(e).__name__.lower()) from None
def gateway_status():
    model=_configured(); out={'generation_model':model,'configured':bool(os.environ.get('LITELLM_MASTER_KEY')),'available':False,'warnings':[]}
    if not out['configured']:out['warnings']=['missing_credentials']; return out
    try:
        status,data=_call('/models'); out['available']=status==200 and any(x.get('id')==model for x in data.get('data',[]))
        if not out['available']:out['warnings']=['model_not_listed']
    except RuntimeError as e:out['warnings']=[str(e)]
    return out
def generate_answer(query,results):
    model=_configured()
    if not results:return {'generation_model':model,'answer':'No matching source passages were found.','answer_mode':'extractive','warnings':['empty_results']}
    passages=[f'[{i}] paper={r.get("paper_title",r.get("paper_id",""))} page={r.get("page","")}\n{r.get("text","")[:1400]}' for i,r in enumerate(results[:5],1)]
    fallback='Source excerpts:\n\n'+'\n\n'.join(passages)
    def _complete(extra=''):
        payload={'model':model,'messages':[{'role':'system','content':'Answer only from the supplied source excerpts. Cite factual claims with [1]-[N], where N is the number of supplied excerpts. Citations must refer only to the excerpt labels [1]-['+str(len(passages))+'] shown above the question; NEVER cite bracketed numbers that appear inside the excerpt text itself. Distinguish observed findings from proposed explanations and state uncertainty. Do not invent citations or biological conclusions.'},{'role':'user','content':f'Question: {query}\n\nSource excerpts:\n'+('\n\n'.join(passages))[:10000]+extra}],'max_tokens':2000,'temperature':0.2}
        started=time.perf_counter(); _,data=_call('/chat/completions',payload,90); msg=data['choices'][0].get('message',{}); finish=data['choices'][0].get('finish_reason')
        text=(msg.get('content') or '')
        text=re.sub(r'<think>.*?</think>','',text,flags=re.S).strip()
        return text,finish,started
    def _ok(text,finish):
        cites=[int(x) for x in re.findall(r'\[(\d+)\]',text)]
        return bool(text) and bool(cites) and all(1<=x<=len(passages) for x in cites) and finish!='length'
    try:
        st=gateway_status()
        if not st['available']:raise RuntimeError((st.get('warnings') or ['gateway_unavailable'])[0])
        text,finish,started=_complete()
        if not _ok(text,finish):
            text,finish,started=_complete('\n\nReminder: cite only the excerpt labels [1]-['+str(len(passages))+']; ignore bracketed numbers inside the excerpts. Write your complete final answer as the message content.')
        cites=[int(x) for x in re.findall(r'\[(\d+)\]',text)]
        if not _ok(text,finish):raise RuntimeError('invalid_or_truncated_answer')
        return {'generation_model':model,'answer':text,'answer_mode':'generated','warnings':['Selected source passages sent through LiteLLM/OpenRouter.','human_review_needed'],'latency_seconds':time.perf_counter()-started}
    except Exception as e:return {'generation_model':model,'answer':fallback,'answer_mode':'extractive','warnings':[str(e),'human_review_needed']}
