import asyncio
import json
import time
import uuid
from fastapi.testclient import TestClient
import pytest
from backend import clean_env_value, create_app, DirectNvidiaChat, load_env_files, Memory, Runtime, apply_telemetry

@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://127.0.0.1:8765') as c:
        c.headers['X-Jarvis-Token']=c.get('/session').json()['token']
        yield c

def event(action='up',**kw):
    return dict(event_id=str(uuid.uuid4()),action=action,**kw)

def test_telemetry_persists_and_deduplicates(client):
    item=event()
    assert client.post('/telemetry',json=item).json()['accepted']
    assert not client.post('/telemetry',json=item).json()['accepted']
    assert client.get('/state').json()['core']['layer']==1
    events=client.get('/state').json()['events']
    assert len([event for event in events if event['kind']=='telemetry'])==1

@pytest.mark.parametrize('payload',[event('execute'),event(x=1001),event('drag'),event(node=-1),event(extra='execute')])
def test_rejects_invalid_telemetry(client,payload):
    assert client.post('/telemetry',json=payload).status_code==422

def test_origin_host_token_boundary(client):
    assert client.post('/telemetry',json=event(),headers={'X-Jarvis-Token':'wrong'}).status_code==403
    assert client.post('/telemetry',json=event(),headers={'Origin':'https://unrelated.example'}).status_code==403
    assert client.get('/session',headers={'Host':'unrelated.example'}).status_code==403
    assert client.post('/telemetry',content='x'*17000).status_code==413

def test_env_helpers_accept_common_local_names(monkeypatch):
    monkeypatch.delenv('NVIDIA_API_KEY', raising=False)
    assert clean_env_value(' "abc123" ') == 'abc123'
    assert '.env.example' not in load_env_files()

def test_unconfigured_runtime_rejects_ai_and_audio(client):
    assert client.post('/message',json={'text':'Hello'}).status_code==503
    assert client.post('/audio',json={'enabled':True}).status_code==503
    assert client.get('/state').json()['status']=='configuration required'

def test_core_mapping_is_bounded():
    assert apply_telemetry({'layer':0},event('down'))['layer']==0
    assert apply_telemetry({'layer':12},event('up'))['layer']==12
    state=apply_telemetry({'layer':0},event('drag',node=3,x=.2,y=.4,z=.6))
    assert state['node']==3 and state['node_position']['x']==.2
    assert 'weights' not in state

def test_restart_preserves_context_and_retrieval(tmp_path):
    store=Memory(tmp_path/'events.sqlite3')
    store.add('user',{'text':'Prepare physics notes'})
    store.set('history',[{'role':'user','content':'Physics'}])
    store.close()
    store=Memory(tmp_path/'events.sqlite3')
    assert store.get('history')[0]['content']=='Physics'
    assert store.retrieve('physics')[0]['body']['text']=='Prepare physics notes'
    store.close()

def test_direct_nvidia_chat_uses_real_completion_shape():
    class Message:
        content='Ready, Sir.'
    class Choice:
        message=Message()
    class Response:
        choices=[Choice()]
    class Completions:
        def create(self, **kw):
            assert kw['model']=='meta/llama-3.3-70b-instruct'
            assert kw['messages'][0]['role']=='system'
            assert kw['messages'][-1]['content']=='Hello'
            return Response()
    class Chat:
        completions=Completions()
    class Client:
        chat=Chat()
    agent=DirectNvidiaChat(Client(),'meta/llama-3.3-70b-instruct','System prompt')
    result=agent.run_conversation(user_message='Hello',conversation_history=[
        {'role':'tool','content':'hidden'},
        {'role':'assistant','content':'Previous answer'},
    ])
    assert result['final_response']=='Ready, Sir.'
    assert result['messages'][-1]['role']=='assistant'

def test_empty_embed_model_does_not_record_semantic_error(tmp_path, monkeypatch):
    class Client:
        chat = object()
        base_url = 'https://integrate.api.nvidia.com/v1'
    class OpenAI:
        def __init__(self, **kw):
            self.chat = Client.chat
            self.base_url = Client.base_url
    monkeypatch.setenv('NVIDIA_API_KEY','test-key')
    monkeypatch.setenv('JARVIS_EMBED_MODEL','')
    monkeypatch.setitem(__import__('sys').modules, 'openai', type('OpenAIModule', (), {'OpenAI': OpenAI}))
    rt = Runtime(tmp_path)
    rt.boot()
    events = rt.memory.recent(10)
    assert rt.status == 'ready'
    assert rt.memory.mode == 'lexical'
    assert not any(event['kind']=='error' and 'Semantic retrieval' in event['body'].get('message','') for event in events)
    asyncio.run(rt.close())

def test_message_endpoint_queues_and_worker_records_reply(client):
    class Agent:
        def run_conversation(self,**kw):
            return {'final_response':'Ready, Sir.','messages':[
                {'role':'user','content':kw['user_message']},
                {'role':'assistant','content':'Ready, Sir.'}]}
    rt = client.app.state.runtime
    rt.agent = Agent()
    rt.status = 'ready'
    response = client.post('/message',json={'text':'Hello'})
    assert response.status_code == 202
    deadline = time.time() + 2
    events = []
    while time.time() < deadline:
        events = client.get('/state').json()['events']
        if any(event['kind']=='assistant' for event in events):
            break
        time.sleep(.05)
    assert any(event['kind']=='queued' and event['body']['text']=='Hello' for event in events)
    assert any(event['kind']=='assistant' and event['body']['text']=='Ready, Sir.' for event in events)

def test_actual_hermes_contract_preserves_tool_history(tmp_path):
    class Agent:
        def run_conversation(self,**kw):
            assert 'RUNTIME DATA' in kw['user_message']
            assert kw['conversation_history']==[]
            return {'final_response':'Ready, Sir.','messages':[
                {'role':'user','content':kw['user_message']},
                {'role':'assistant','content':None,'tool_calls':[{'id':'a','type':'function','function':{'name':'memory','arguments':'{}'}}]},
                {'role':'tool','tool_call_id':'a','content':'Done'},
                {'role':'assistant','content':'Ready, Sir.'}]}
    rt=Runtime(tmp_path)
    rt.agent=Agent()
    assert rt.turn('Hello','keyboard')=='Ready, Sir.'
    assert rt.memory.get('history')[2]['role']=='tool'
    assert rt.memory.recent()[-1]['kind']=='assistant'
    asyncio.run(rt.close())

def test_rate_limit_is_observable(client):
    statuses=[client.post('/telemetry',json=event()).status_code for _ in range(31)]
    assert statuses[-1]==429

def test_pages_and_security_headers(client):
    for url in ('/','/dashboard'):
        r=client.get(url)
        assert r.status_code==200
        assert "frame-ancestors 'none'" in r.headers['content-security-policy']
