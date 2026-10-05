import unittest, os
from unittest.mock import patch
import sys
sys.path.insert(0, __import__('pathlib').Path(__file__).parents[1].as_posix())
import gateway
R=[{'paper_id':'p','page':2,'text':'FST1 was measured in the sample.'}]
class GatewayTests(unittest.TestCase):
 def test_empty_no_call(self):
  with patch.object(gateway,'_call') as c: self.assertEqual(gateway.generate_answer('x',[])['answer_mode'],'extractive'); c.assert_not_called()
 def test_missing_key(self):
  with patch.dict(os.environ,{},clear=True): self.assertEqual(gateway.generate_answer('x',R)['answer_mode'],'extractive')
 def test_valid(self):
  with patch.object(gateway,'gateway_status',return_value={'generation_model':'anthropic/claude-haiku-4.5','available':True,'warnings':[]}), patch.object(gateway,'_call',return_value=(200,{'choices':[{'message':{'content':'FST1 was measured [1].'}}]})):
   self.assertEqual(gateway.generate_answer('x',R)['answer_mode'],'generated')
 def test_invalid_fallback(self):
  with patch.object(gateway,'gateway_status',return_value={'generation_model':'x','available':True,'warnings':[]}), patch.object(gateway,'_call',return_value=(200,{'choices':[{'message':{'content':'unsupported claim'}}]})):
   self.assertEqual(gateway.generate_answer('x',R)['answer_mode'],'extractive')
 def test_think_tags_stripped(self):
  with patch.object(gateway,'gateway_status',return_value={'generation_model':'deepseek/deepseek-v4.1-flash','available':True,'warnings':[]}), patch.object(gateway,'_call',return_value=(200,{'choices':[{'message':{'content':'<think>reasoning here</think>FST1 was measured [1].'},'finish_reason':'stop'}]})):
   out=gateway.generate_answer('x',R); self.assertEqual(out['answer_mode'],'generated'); self.assertNotIn('<think>',out['answer'])
 def test_reasoning_only_falls_back(self):
  with patch.object(gateway,'gateway_status',return_value={'generation_model':'deepseek/deepseek-v4.1-flash','available':True,'warnings':[]}), patch.object(gateway,'_call',return_value=(200,{'choices':[{'message':{'content':'','reasoning_content':'long reasoning without final answer'},'finish_reason':'stop'}]})):
   self.assertEqual(gateway.generate_answer('x',R)['answer_mode'],'extractive')
 def test_truncation_falls_back(self):
  with patch.object(gateway,'gateway_status',return_value={'generation_model':'deepseek/deepseek-v4.1-flash','available':True,'warnings':[]}), patch.object(gateway,'_call',return_value=(200,{'choices':[{'message':{'content':'FST1 was measured [1].'},'finish_reason':'length'}]})):
   out=gateway.generate_answer('x',R); self.assertEqual(out['answer_mode'],'extractive'); self.assertIn('invalid_or_truncated_answer',out['warnings'])
 def test_rate_limit_falls_back(self):
  with patch.object(gateway,'gateway_status',return_value={'generation_model':'deepseek/deepseek-v4.1-flash','available':True,'warnings':[]}), patch.object(gateway,'_call',side_effect=RuntimeError('http_429')):
   out=gateway.generate_answer('x',R); self.assertEqual(out['answer_mode'],'extractive'); self.assertIn('http_429',out['warnings'])
 def test_empty_content_retries_once(self):
  with patch.object(gateway,'gateway_status',return_value={'generation_model':'deepseek/deepseek-v4.1-flash','available':True,'warnings':[]}), patch.object(gateway,'_call',side_effect=[(200,{'choices':[{'message':{'content':''},'finish_reason':'stop'}]}),(200,{'choices':[{'message':{'content':'FST1 was measured [1].'},'finish_reason':'stop'}]})]) as c:
   out=gateway.generate_answer('x',R); self.assertEqual(out['answer_mode'],'generated'); self.assertEqual(c.call_count,2)
 def test_retry_still_empty_falls_back(self):
  with patch.object(gateway,'gateway_status',return_value={'generation_model':'deepseek/deepseek-v4.1-flash','available':True,'warnings':[]}), patch.object(gateway,'_call',side_effect=[(200,{'choices':[{'message':{'content':''},'finish_reason':'stop'}]}),(200,{'choices':[{'message':{'content':''},'finish_reason':'stop'}]})]) as c:
   out=gateway.generate_answer('x',R); self.assertEqual(out['answer_mode'],'extractive'); self.assertEqual(c.call_count,2)
if __name__=='__main__': unittest.main()
