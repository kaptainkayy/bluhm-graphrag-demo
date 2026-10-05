import json, threading, unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import sys
sys.path.insert(0,'.')
import backend

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=backend.ThreadingHTTPServer(('127.0.0.1',0),backend.Handler); cls.t=threading.Thread(target=cls.s.serve_forever,daemon=True); cls.t.start(); cls.base='http://127.0.0.1:%d'%cls.s.server_port
    @classmethod
    def tearDownClass(cls): cls.s.shutdown(); cls.s.server_close()
    def get(self,p):
        with urlopen(self.base+p) as r:return r.status,r.headers.get_content_type(),r.read()
    def test_status_static_and_graph(self):
        code,_,b=self.get('/api/status'); self.assertEqual(code,200); self.assertTrue(all(k in json.loads(b) for k in ('ready','papers','pages','chunks','entities','edges','answer_mode')))
        self.assertEqual(self.get('/')[0],200); self.assertEqual(self.get('/api/graph?limit=1')[0],200)
    def test_search_and_validation(self):
        data=json.dumps({'query':'FST1 maize','limit':2}).encode(); r=urlopen(Request(self.base+'/api/search',data=data,headers={'Content-Type':'application/json'})); out=json.loads(r.read()); self.assertTrue(out['results']); self.assertTrue(out['results'][0]['id'])
        for body in ('[]',json.dumps({'query':'x','limit':-1}),json.dumps({'query':[]})):
            with self.assertRaises(HTTPError) as x:urlopen(Request(self.base+'/api/search',data=body.encode()))
            self.assertEqual(x.exception.code,400)
    def test_security(self):
        with self.assertRaises(HTTPError) as x:urlopen(self.base+'/../backend.py')
        self.assertEqual(x.exception.code,404)

if __name__=='__main__': unittest.main()
