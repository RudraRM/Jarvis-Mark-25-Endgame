"""Local JARVIS gateway. Run one process: python backend.py [--demo]."""
from __future__ import annotations
import argparse
import asyncio
import concurrent.futures
import contextlib
import datetime as dt
import json
import logging
import multiprocessing as mp
import os
from pathlib import Path
import queue
import re
import secrets
import sqlite3
import sys
import threading
import time
import uuid
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent
LOG = logging.getLogger('jarvis')

def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()

class Telemetry(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    event_id: uuid.UUID
    action: Literal['twist', 'turn', 'up', 'down', 'drag', 'dragged inside core dots']
    x: float = Field(default=0, ge=-1000, le=1000)
    y: float = Field(default=0, ge=-1000, le=1000)
    z: float = Field(default=0, ge=-1000, le=1000)
    node: int | None = Field(default=None, ge=0, le=99999)

class Message(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=8000)

class Toggle(BaseModel):
    enabled: bool

class Memory:
    """One durable stream; vectors are local, raw audio is never persisted."""
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL,
            ts TEXT NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL,
            vector TEXT, embedding_model TEXT);
          CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')
        self.db.commit()
        self.encoder = None
        self.model_name = ''
        self.mode = 'lexical'

    def set(self, key, value):
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO state VALUES (?,?)', (key, json.dumps(value)))

    def get(self, key, default=None):
        with self.lock:
            row = self.db.execute('SELECT value FROM state WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def add(self, kind, body, event_id=None):
        with self.lock, self.db:
            cur = self.db.execute('INSERT OR IGNORE INTO events(event_id,ts,kind,body) VALUES(?,?,?,?)',
                (event_id or str(uuid.uuid4()), utc(), kind, json.dumps(body, ensure_ascii=False)))
            return cur.rowcount == 1

    def accept_telemetry(self, item, state):
        with self.lock, self.db:
            cur = self.db.execute('INSERT OR IGNORE INTO events(event_id,ts,kind,body) VALUES(?,?,?,?)',
                (item['event_id'],utc(),'telemetry',json.dumps(item)))
            if not cur.rowcount:
                return False, state
            updated = apply_telemetry(state,item)
            self.db.execute('INSERT OR REPLACE INTO state VALUES (?,?)',('core',json.dumps(updated)))
            return True, updated

    def recent(self, limit=16):
        with self.lock:
            rows = self.db.execute('SELECT id,ts,kind,body FROM events ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        return [dict(id=r[0], ts=r[1], kind=r[2], body=json.loads(r[3])) for r in reversed(rows)]

    def enable_semantic(self, name):
        if not name:
            return
        from sentence_transformers import SentenceTransformer
        self.encoder = SentenceTransformer(name)
        self.model_name = name
        self.mode = 'semantic'

    def retrieve(self, query_text, limit=6):
        qwords = set(re.findall(r'\w+', query_text.lower()))
        with self.lock:
            cutoff = self.db.execute('SELECT COALESCE(MAX(id),0) FROM events').fetchone()[0]
        if self.encoder:
            # Backfill persisted events without losing historical records on restart.
            while True:
                with self.lock:
                    pending = self.db.execute('SELECT id,body FROM events WHERE id<=? AND (vector IS NULL OR embedding_model != ?) LIMIT 64',
                                              (cutoff,self.model_name)).fetchall()
                if not pending:
                    break
                vectors = self.encoder.encode([r[1] for r in pending], normalize_embeddings=True)
                with self.lock, self.db:
                    self.db.executemany('UPDATE events SET vector=?,embedding_model=? WHERE id=?',
                        [(json.dumps(v.tolist()), self.model_name, r[0]) for r, v in zip(pending, vectors)])
            qv = self.encoder.encode(query_text, normalize_embeddings=True).tolist()
        ranked = []
        with self.lock:
            cursor = self.db.execute('SELECT id,ts,kind,body,vector FROM events WHERE id<=?',(cutoff,))
            for ident, ts, kind, body, vector in cursor:
                if self.encoder and vector:
                    score = sum(a*b for a,b in zip(qv, json.loads(vector)))
                else:
                    words = set(re.findall(r'\w+', body.lower()))
                    score = len(qwords & words) / max(1, len(qwords | words))
                if score > 0:
                    ranked.append((score, ident, ts, kind, body))
                    ranked = sorted(ranked, reverse=True)[:limit]
        return [dict(id=i, ts=t, kind=k, body=json.loads(b), score=round(s,4)) for s,i,t,k,b in ranked]

    def close(self):
        with self.lock:
            self.db.close()


def apply_telemetry(state, event):
    state = dict(state)
    action = event['action']
    state['last_action'] = action
    if action in ('twist','turn'):
        state['orientation'] = {k:event.get(k,0) for k in ('x','y','z')}
        state['focus'] = 'Diagnostic sweep'
    elif action in ('up','down'):
        state['layer'] = max(0, min(12, state.get('layer',0) + (1 if action=='up' else -1)))
        state['focus'] = 'Navigation layer'
    else:
        state['node'] = event.get('node')
        state['node_position'] = {k:event.get(k,0) for k in ('x','y','z')}
        state['focus'] = 'Core parameter inspection'
    return state


def tts_process(inbox, statuses, speaking, voice, rate):
    """Dedicated process keeps OS TTS ownership out of the ASGI event loop."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty('rate', rate)
        voices = engine.getProperty('voices') or []
        match = next((v for v in voices if voice and voice.lower() in (v.id+' '+v.name).lower()), None)
        if not match and not voice:
            match = next((v for v in voices if any(s in (v.id+' '+v.name).lower() for s in ('en-gb','british','daniel'))), None)
        if match:
            engine.setProperty('voice', match.id)
        statuses.put(('tts', 'ready'))
        while True:
            text = inbox.get()
            if text is None:
                break
            speaking.set()
            try:
                engine.say(text)
                engine.runAndWait()
            finally:
                speaking.clear()
        engine.stop()
    except Exception as exc:
        statuses.put(('tts', 'unavailable: '+type(exc).__name__))
    finally:
        speaking.clear()

class Audio:
    def __init__(self, runtime):
        self.rt = runtime
        self.stop = threading.Event()
        self.frames = queue.Queue(maxsize=50)
        self.threads = []
        self.call = None
        self.dropped = 0

    def start(self):
        if any(t.is_alive() for t in self.threads):
            raise RuntimeError('Previous audio workers are still stopping')
        self.stop.clear()
        self.frames = queue.Queue(maxsize=50)
        self.threads = [threading.Thread(target=self.capture, daemon=True), threading.Thread(target=self.recognize, daemon=True)]
        for thread in self.threads:
            thread.start()

    def halt(self):
        self.stop.set()
        if self.call is not None:
            self.call.cancel()
        for thread in self.threads:
            thread.join(timeout=3)
        self.rt.audio_status = 'muted'

    def capture(self):
        pa = stream = None
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            stream = pa.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1600)
            while not self.stop.is_set():
                chunk = stream.read(1600, exception_on_overflow=True)
                # Half-duplex: don't transcribe JARVIS speaking through the speakers.
                if self.rt.speaking.is_set():
                    chunk = bytes(len(chunk))
                try:
                    self.frames.put_nowait(chunk)
                except queue.Full:
                    self.dropped += 1
                    self.rt.audio_status = 'audio overflow'
        except Exception as exc:
            self.rt.audio_status = 'microphone unavailable: '+type(exc).__name__
            self.rt.post_event('error', {'component':'microphone','message':self.rt.audio_status})
            self.stop.set()
            if self.call is not None:
                self.call.cancel()
        finally:
            if stream:
                stream.close()
            if pa:
                pa.terminate()

    def chunks(self):
        while not self.stop.is_set():
            try:
                yield self.frames.get(timeout=.25)
            except queue.Empty:
                continue

    def recognize(self):
        auth = None
        try:
            import riva.client
            from riva.client.asr import streaming_request_generator
            metadata = []
            function_id = os.getenv('RIVA_FUNCTION_ID','')
            if function_id:
                metadata = [('function-id',function_id), ('authorization','Bearer '+os.environ['NVIDIA_API_KEY'])]
            auth = riva.client.Auth(uri=os.getenv('RIVA_SERVER','localhost:50051'),
                use_ssl=os.getenv('RIVA_USE_SSL','0')=='1', metadata_args=metadata)
            service = riva.client.ASRService(auth)
            config = riva.client.StreamingRecognitionConfig(
                config=riva.client.RecognitionConfig(encoding=riva.client.AudioEncoding.LINEAR_PCM,
                    sample_rate_hertz=16000, audio_channel_count=1,
                    language_code=os.getenv('RIVA_LANGUAGE','en-US'),
                    model=os.getenv('RIVA_MODEL',''), enable_automatic_punctuation=True), interim_results=True)
            delay = 1
            while not self.stop.is_set():
                try:
                    self.rt.audio_status = 'connecting'
                    self.call = service.stub.StreamingRecognize(
                        streaming_request_generator(self.chunks(), config), metadata=auth.get_auth_metadata(), timeout=240)
                    for response in self.call:
                        self.rt.audio_status = 'listening'
                        delay = 1
                        for result in response.results:
                            if result.is_final and result.alternatives:
                                transcript = result.alternatives[0].transcript.strip()
                                if transcript and not self.rt.speaking.is_set():
                                    self.rt.post_transcript(transcript)
                except Exception as exc:
                    if self.stop.is_set():
                        break
                    self.rt.audio_status = 'ASR reconnecting: '+type(exc).__name__
                    self.rt.post_event('error', {'component':'ASR','message':self.rt.audio_status})
                    # Discard stale raw audio after a failed stream; never replay commands.
                    while True:
                        try:
                            self.frames.get_nowait()
                            self.dropped += 1
                        except queue.Empty:
                            break
                    self.stop.wait(delay)
                    delay = min(delay*2, 20)
        except Exception as exc:
            self.rt.audio_status = 'ASR unavailable: '+type(exc).__name__
            self.rt.post_event('error', {'component':'ASR','message':self.rt.audio_status})
            self.stop.set()
        finally:
            if auth:
                auth.channel.close()

class Runtime:
    def __init__(self, data_dir, demo=False):
        self.demo = demo
        self.memory = Memory(data_dir/'events.sqlite3')
        self.session_id = self.memory.get('session_id') or str(uuid.uuid4())
        self.memory.set('session_id',self.session_id)
        self.core = self.memory.get('core', {'layer':0,'node':None,'focus':'Awaiting input'})
        self.token = secrets.token_urlsafe(32)
        self.agent = None
        self.client = None
        self.history = self.memory.get('history',[])
        self.status = 'visual demo' if demo else 'starting'
        self.audio_status = 'muted'
        self.tts_status = 'off'
        self.started = time.monotonic()
        self.jobs = asyncio.Queue(maxsize=16)
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix='hermes')
        ctx = mp.get_context('spawn')
        self.speaking = ctx.Event()
        self.tts_queue = ctx.Queue(maxsize=8)
        self.tts_events = ctx.Queue()
        self.tts = None
        self.audio = Audio(self)
        self.loop = None
        self.count = 0
        self.closed = False

    def post_event(self, kind, body):
        if not self.closed:
            self.memory.add(kind,body)

    def post_transcript(self, text):
        if self.loop and not self.closed:
            self.loop.call_soon_threadsafe(self.accept_audio, text)

    def accept_audio(self, text):
        self.memory.add('transcript', {'text':text})
        try:
            self.jobs.put_nowait((text,'microphone'))
        except asyncio.QueueFull:
            self.memory.add('error', {'message':'Transcript stored but not executed: command queue full'})

    def boot(self):
        if self.demo:
            return
        try:
            path = Path(os.environ['HERMES_AGENT_PATH']).expanduser().resolve()
            if not (path/'run_agent.py').is_file():
                raise RuntimeError('HERMES_AGENT_PATH must contain run_agent.py')
            sys.path.insert(0,str(path))
            from openai import OpenAI
            from run_agent import AIAgent
            key = os.environ['NVIDIA_API_KEY']
            if not key:
                raise RuntimeError('Set NVIDIA_API_KEY in .env')
            # Official OpenAI-compatible NVIDIA client; AIAgent owns tool iterations.
            self.client = OpenAI(api_key=key, base_url=os.getenv('JARVIS_LLM_BASE_URL','https://integrate.api.nvidia.com/v1'),
                                 timeout=60, max_retries=2)
            self.agent = AIAgent(api_key=key, base_url=str(self.client.base_url),
                model=os.getenv('JARVIS_MODEL','meta/llama-3.3-70b-instruct'),
                enabled_toolsets=[t.strip() for t in os.getenv('JARVIS_TOOLSETS','memory,session_search,skills').split(',') if t.strip()],
                max_iterations=12, run_budget_seconds=120, session_id=self.session_id,
                ephemeral_system_prompt=(ROOT/'prompt.txt').read_text(), quiet_mode=True,
                skip_memory=False, skip_background_review=True)
            try:
                self.memory.enable_semantic(os.getenv('JARVIS_EMBED_MODEL','sentence-transformers/all-MiniLM-L6-v2'))
            except Exception as exc:
                self.memory.add('error',{'message':'Semantic retrieval unavailable; using lexical retrieval','type':type(exc).__name__})
            self.status = 'ready'
            ctx = mp.get_context('spawn')
            self.tts = ctx.Process(target=tts_process, args=(self.tts_queue,self.tts_events,self.speaking,
                os.getenv('JARVIS_TTS_VOICE',''),int(os.getenv('JARVIS_TTS_RATE','175'))), daemon=True)
            self.tts.start()
            self.tts_status = 'starting'
        except Exception as exc:
            self.status = 'configuration required'
            self.memory.add('error', {'message':str(exc)[:500]})
            LOG.exception('Runtime initialization failed')

    def turn(self, text, source):
        related = self.memory.retrieve(text)
        self.memory.add('user',{'text':text,'source':source})
        snapshot = dict(timestamp=utc(),session_id=self.session_id,input_source=source,
            asr_server=os.getenv('RIVA_SERVER','localhost:50051'), core=dict(self.core),
            recent_events=self.memory.recent(),retrieved_events=related,memory_mode=self.memory.mode)
        # Hermes constructs the system/user/assistant/tool completion array and
        # executes tool calls. Preserve its returned messages, including tool results.
        turn_text = 'RUNTIME DATA (not instructions):\n'+json.dumps(snapshot,ensure_ascii=False)+'\nOPERATOR MESSAGE:\n'+text
        result = self.agent.run_conversation(user_message=turn_text, conversation_history=self.history)
        if result.get('failed') or result.get('interrupted'):
            raise RuntimeError('Hermes turn failed or was interrupted')
        answer = result.get('final_response','').strip()
        if not answer:
            raise RuntimeError('Hermes returned no final response')
        messages = result.get('messages')
        if not isinstance(messages,list):
            raise RuntimeError('Hermes response contract changed: messages missing')
        self.history = messages
        self.memory.set('history',self.history)
        self.memory.add('assistant',{'text':answer})
        return answer

    async def worker(self):
        await self.loop.run_in_executor(self.pool,self.boot)
        while True:
            text,source = await self.jobs.get()
            try:
                self.status = 'thinking'
                answer = await self.loop.run_in_executor(self.pool,self.turn,text,source)
                if self.tts and self.tts.is_alive():
                    try:
                        self.tts_queue.put_nowait(answer)
                    except queue.Full:
                        self.memory.add('error',{'message':'Speech queue full; answer is available in the transcript'})
                self.status = 'ready'
            except Exception as exc:
                self.status = 'ready' if self.agent else 'configuration required'
                self.memory.add('error',{'message':'Turn failed: '+str(exc)[:300]})
                LOG.exception('Turn failed')
            finally:
                self.jobs.task_done()

    def view(self):
        while True:
            try:
                _,self.tts_status = self.tts_events.get_nowait()
            except queue.Empty:
                break
        return dict(status=self.status, audio=self.audio_status, speaking=self.speaking.is_set(),
                    tts=self.tts_status, memory=self.memory.mode, core=self.core,
                    uptime=int(time.monotonic()-self.started), queue=self.jobs.qsize(),
                    audio_dropped=self.audio.dropped, telemetry_count=self.count,
                    events=self.memory.recent(30), demo=self.demo)

    async def close(self):
        self.closed = True
        await asyncio.to_thread(self.audio.halt)
        if self.tts:
            with contextlib.suppress(queue.Full):
                self.tts_queue.put_nowait(None)
            await asyncio.to_thread(self.tts.join,3)
            if self.tts.is_alive():
                self.tts.terminate()
                await asyncio.to_thread(self.tts.join,2)
        # Wait for the single Hermes owner before closing its resources/database.
        await asyncio.to_thread(self.pool.shutdown,True,cancel_futures=True)
        if self.agent and hasattr(self.agent,'close'):
            self.agent.close()
        if self.client:
            self.client.close()
        self.memory.close()


def create_app(data_dir=None, demo=False):
    rt = Runtime(Path(data_dir or ROOT/'data'),demo)
    @contextlib.asynccontextmanager
    async def lifespan(app):
        rt.loop = asyncio.get_running_loop()
        worker = asyncio.create_task(rt.worker())
        yield
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker
        await rt.close()
    app = FastAPI(title='JARVIS Local Gateway',lifespan=lifespan,docs_url=None,redoc_url=None)
    app.state.runtime = rt
    rates = {}

    @app.middleware('http')
    async def boundary(request: Request, call_next):
        port = os.getenv('JARVIS_PORT','8765')
        hosts = {'127.0.0.1:'+port,'localhost:'+port}
        host = request.headers.get('host','')
        if host not in hosts:
            return JSONResponse({'detail':'Local host required'},status_code=403)
        origin = request.headers.get('origin')
        if origin and origin != 'http://'+host:
            return JSONResponse({'detail':'Same origin required'},status_code=403)
        if request.method == 'POST':
            token = request.headers.get('x-jarvis-token','')
            if not secrets.compare_digest(token,rt.token):
                return JSONResponse({'detail':'Session token required'},status_code=403)
            # Read with a real cap, including requests without Content-Length.
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body)>16384:
                    return JSONResponse({'detail':'Payload too large'},status_code=413)
            request._body = bytes(body)
            key = request.url.path
            now = time.monotonic()
            previous = [t for t in rates.get(key,[]) if now-t<1]
            if len(previous)>=30:
                return JSONResponse({'detail':'Rate limit exceeded'},status_code=429)
            rates[key] = previous+[now]
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; connect-src 'self' https://cdn.jsdelivr.net; img-src 'self' data:; frame-ancestors 'none'"
        return response

    @app.get('/')
    async def index():
        return FileResponse(ROOT/'web/index.html')

    @app.get('/dashboard')
    async def dashboard():
        return FileResponse(ROOT/'web/dashboard.html')

    @app.get('/health')
    async def health():
        return {'gateway':'running','runtime':rt.status}

    @app.get('/session')
    async def session():
        return {'token':rt.token}

    @app.get('/state')
    async def state():
        return rt.view()

    @app.post('/telemetry')
    async def telemetry(event: Telemetry):
        item = event.model_dump(mode='json')
        if event.action in ('drag','dragged inside core dots') and event.node is None:
            raise HTTPException(422,'Node required for a core drag')
        accepted, rt.core = rt.memory.accept_telemetry(item,rt.core)
        if accepted:
            rt.count += 1
        return {'accepted':accepted,'core':rt.core}

    @app.post('/message',status_code=202)
    async def message(body: Message):
        if not body.text.strip():
            raise HTTPException(422,'Message is empty')
        if not rt.agent or rt.status == 'configuration required':
            raise HTTPException(503,'Hermes is unavailable. Configure the local runtime first.')
        try:
            rt.jobs.put_nowait((body.text.strip(),'keyboard'))
        except asyncio.QueueFull:
            raise HTTPException(429,'Command queue full')
        return {'queued':True}

    @app.post('/audio')
    async def audio(body: Toggle):
        if body.enabled:
            if not rt.agent:
                raise HTTPException(503,'Configure Hermes before enabling microphone capture')
            try:
                rt.audio.start()
            except RuntimeError as exc:
                raise HTTPException(409,str(exc))
        else:
            await asyncio.to_thread(rt.audio.halt)
        return {'enabled':body.enabled}
    return app

if __name__ == '__main__':
    from dotenv import load_dotenv
    import uvicorn
    load_dotenv(ROOT/'.env')
    parser = argparse.ArgumentParser()
    parser.add_argument('--demo',action='store_true',help='Visual and telemetry preview without microphone/model')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(demo=args.demo),host='127.0.0.1',port=int(os.getenv('JARVIS_PORT','8765')),workers=1)
