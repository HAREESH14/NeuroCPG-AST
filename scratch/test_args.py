import sys
sys.path.insert(0, 'scripts')
import resubmission_independent_judge as r
class MockResponse:
    class Message:
        content = '{"hallucinations_found": 0, "is_equivalent": true, "explanation": "Match"}'
    choices = [type('Choice', (), {'message': Message()})()]
def mc(**kwargs):
    print('KWARGS:', kwargs)
    return MockResponse()
r.litellm.completion = mc
r.judge_translation('c', 'j', 'llama3.1:8b', ollama_url='http://a')
