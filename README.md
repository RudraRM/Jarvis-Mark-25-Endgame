# J.A.R.V.I.S. — Mark-85 / Endgame

A local Python voice gateway, a blue Three.js particle-core dashboard, and a dark landing page. The orange core reference informs the particle shell; the dashboard reference informs the surrounding panels, not the central graphic. The core is a procedural interpretation, not a pixel-exact reconstruction of a 3D object from one image.

Read **[JARVIS_IMPLEMENTATION.md](JARVIS_IMPLEMENTATION.md)** for the comprehensive document with architecture, the three-tier prompt, and all authored source files in one executable extraction block.

## What runs

- `/`: landing page with animated blue core, capabilities, architecture, and dashboard entry.
- `/dashboard`: orbit/pan/zoom, shift-drag node selection, keyboard rotation and layer controls, actual runtime states, local command entry, and activity transcript.
- `backend.py`: FastAPI, real NVIDIA chat fallback, optional persistent Hermes AIAgent, bounded command queue, 16 kHz mono PCM microphone capture, Parakeet Riva streaming, and a separate local TTS process.
- `prompt.txt`: stable identity, telemetry/memory context, and volatile runtime state assembly.
- `skills/jarvis/SKILL.md`: installable Hermes operating skill.
- SQLite WAL event history with built-in lexical retrieval. Optional local sentence-transformers embeddings can enable semantic retrieval when configured. Hermes keeps its own memory and tool history too.

**NVIDIA API correction:** the documented Parakeet 1.1B hosted interface is Riva gRPC, not an OpenAI audio-transcription endpoint. The backend uses `from openai import OpenAI` for the NVIDIA-compatible LLM client configuration. If `HERMES_AGENT_PATH` is configured, it embeds the actual Hermes AIAgent for model requests and tool iteration. If Hermes is not configured yet, the dashboard chatbot still works through a real NVIDIA chat completion route. It does not send audio to an invented `/audio/transcriptions` URL. See [NVIDIA's API instructions](https://build.nvidia.com/nvidia/parakeet-1_1b-rnnt-multilingual-asr/api).

## Start the real website

Use Python 3.11–3.13. From the repository directory:

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -r requirements.txt
    python setup.py
    python backend.py

Open **http://127.0.0.1:8765**. The website requires your NVIDIA key for chat; there is no demo runtime or simulated response path. The backend loads `.env`, `.env.local`, or `env.local`, in that order. On Windows, activate with `.venv\Scripts\activate`.


Each HTML page contains its application CSS and JavaScript. Three.js and OrbitControls load from a pinned jsDelivr version, so first-page loading requires internet access. Serve through the gateway, not `file://`. This is not an offline-vendored frontend bundle.

## Full local installation

1. Install Python 3.11–3.13 and Git. Install PortAudio before PyAudio. On macOS: `brew install portaudio`. On Ubuntu/Debian: `sudo apt-get install portaudio19-dev python3-dev espeak-ng`. Windows PyAudio wheels include PortAudio on supported Python versions; use an appropriate system TTS voice. Grant microphone permission to the Python/terminal application on your operating system.
2. Create and activate the virtual environment as above.
3. Install Hermes at the inspected revision and initialize its submodules:

       git clone https://github.com/NousResearch/hermes-agent.git ../hermes-agent
       git -C ../hermes-agent checkout b7b35a84b7fbe1aa2e223a6ce726a2471300d0a4
       git -C ../hermes-agent submodule update --init --recursive
       python -m pip install -e ../hermes-agent
       python -m pip install -r requirements.txt

4. Configure credentials locally:

       python setup.py

   The hidden prompt asks for your NVIDIA API key. No secret is bundled. Existing `.env` files are preserved. This is enough for the dashboard text chatbot to use the configured NVIDIA language model. If you make the file manually, name it `.env`, `.env.local`, or `env.local`; do not commit it.

   To enable full Hermes tool-loop mode and install the JARVIS skill, run setup with the Hermes checkout:

       python setup.py --hermes-path ../hermes-agent --install-skill

   Existing skills are preserved. The default recognizer is a separately deployed local Parakeet NIM at `localhost:50051`.

   To use the hosted NVIDIA recognizer instead, run the setup command with `--hosted-asr` on first configuration. This selects the function ID documented by NVIDIA. Verify model/API availability in your NVIDIA account. Model access, service charges, and rate limits depend on that account.

5. For local ASR, deploy the Parakeet RNNT model using [NVIDIA's GPU/NIM deployment instructions](https://docs.nvidia.com/nim/speech/latest/asr/deploy-asr-models/parakeet-rnnt.html). Select a streaming profile supported by your GPU. This server is a separate prerequisite; an ordinary CPU laptop is not assumed to host the 1.1B NIM. The gateway itself can run on a laptop and connect to a suitable ASR server. If you deploy a different Parakeet model or profile, set `RIVA_MODEL` and the endpoint accordingly.
6. Start `python backend.py`, open the homepage, enter the dashboard, and wait for Ready. Select Listen to start default-microphone capture. Local TTS plays through the gateway machine's speakers. Use headphones for best results. The microphone is muted during TTS; this is half-duplex interaction, not acoustic echo cancellation or barge-in.

Hermes's Python API was inspected at the pinned revision; upstream changes may require an adapter update. Without `HERMES_AGENT_PATH`, the dashboard runs in `nvidia-direct` mode: it can chat through the configured NVIDIA model, but it does not expose Hermes memory/session/tool execution. With `HERMES_AGENT_PATH`, the default toolsets are `memory,session_search,skills`. Additional Hermes toolsets may be explicitly configured with `JARVIS_TOOLSETS`; normal Hermes approval behavior remains in force. The gateway does not bypass interactive tool approvals or silently grant arbitrary terminal/device access.

## Application and gateway architecture

The outer application loop continuously accepts audio and UI events while a single worker owns Hermes. The Hermes inner loop performs completion → tool calls → tool results → follow-up completion until it has final text or reaches the iteration/time budget. `run_conversation(user_message=..., conversation_history=...)` is the actual integration point. Returned `messages`, including assistant tool calls and tool results, persist unchanged for continuation.

The microphone worker reads 1,600 frames per chunk: 100 ms of 16,000 Hz mono signed 16-bit PCM from the default input device. A bounded queue feeds Riva's streaming gRPC request generator. Interim ASR results do not trigger actions; only final transcripts enter the command queue. ASR reconnects with bounded backoff. Stale frames after failed streams are discarded and the dropped-frame count is displayed. Raw audio is never written to SQLite.

Validated `/telemetry` events update the current context immediately and are persisted transactionally with core state. Gestures do not initiate an expensive LLM completion for every pointer pixel. The next queued operator message includes current telemetry, recent events, relevant past events, input source, session ID, and timestamp. Accepted UI events are durable; the browser coalesces intermediate movement when delivery is busy. It reports failed delivery rather than promising zero-loss real-time networking.

`Memory.retrieve` uses lexical ranking by default, so no extra embedding model is required for the chatbot to run. If `JARVIS_EMBED_MODEL` is set, it embeds pending historical records in batches using a local sentence-transformers model and ranks records by normalized vector similarity at read time. If that optional semantic setup fails, the gateway stays in lexical mode and records a system note instead of an error. Finite retrieval and finite model context are not perfect, unlimited recall.

Only the final conversational reply is passed to pyttsx3. A separate process owns the TTS engine; failures are visible. A British voice is selected when installed, otherwise the system voice is used. Set `JARVIS_TTS_VOICE` to a matching installed name/ID to select a voice explicitly.

The 3-tier assembly is an application prompt convention requested for this project, not a claimed official Hermes-wide standard. `prompt.txt` stays stable; live JSON is appended to each turn as untrusted runtime data. Hermes still applies its own base/tool instructions.

## Telemetry contract

All POST requests require the per-process `X-Jarvis-Token` obtained from same-origin `/session`. Browser requests are same-origin only. The server binds to loopback, rejects unrecognized Host/Origin values, caps bodies at 16 KiB, rate-limits writes, and validates fields. Do not bind this implementation to a public interface without a separate authenticated deployment design.

| Action | Required data | Actual local effect |
|---|---|---|
| `twist`, `turn` | UUID `event_id`; bounded optional `x,y,z` | Set virtual diagnostic orientation |
| `up`, `down` | UUID `event_id` | Move virtual layer within 0–12 |
| `drag`, `dragged inside core dots` | UUID `event_id`, `node`; optional `x,y,z` | Focus a particle node and retain its local coordinates |

No gesture changes real neural weights, security clearances, root directories, or physical power systems. Such integrations require implemented tools and explicit operator instructions.

| Endpoint | Purpose |
|---|---|
| `GET /health` | Gateway and runtime readiness |
| `GET /session` | Same-origin per-process UI token |
| `GET /state` | Actual runtime state and recent activity |
| `POST /telemetry` | Validate, deduplicate, and persist a gesture |
| `POST /message` | Queue a keyboard message; 202 means queued, not completed |
| `POST /audio` | Enable or stop microphone workers |

The command queue is in memory and is not an exactly-once durable job system. A process crash can interrupt queued/in-flight requests. Confirm outcomes in the transcript before resubmitting consequential commands. Event and conversation records persist. Ctrl+C shuts down audio and speech, waits for the active Hermes owner, and closes resources. The model time budget limits normal turns; dependency/network shutdown behavior also depends on upstream libraries.

## Data and recovery

`data/events.sqlite3` stores event history, core state, session identity, and Hermes continuation messages. `data/` and `.env` are ignored by Git. For a private desktop setup, keep the repository and data directory under your OS user account; database contents are not encrypted by this app. Stop the app before backing up or deleting the database, including its WAL/SHM files. Hermes also stores its own memory/session data under its configured home; resetting the gateway does not erase that separate history.

Runtime setup errors appear in the activity feed. A ready process does not prove the configured model or ASR service will accept the next request. Check account permissions, model availability, endpoint reachability, audio drivers, and installed voices when failures appear. If the NVIDIA key is valid but chat fails, verify that your account has access to `JARVIS_MODEL`; you can replace it with another NVIDIA-hosted chat model ID available in your account. Voice capture is on the Python machine, not on a remote browser device.

## Verification and limits

Run `python -m pip install pytest httpx`, then `python -m pytest -q`.

The included tests cover telemetry validation, deduplication, persistence, origin/host/token boundaries, body limits, queue rate limits, direct NVIDIA chat mode wiring, honest failure when the NVIDIA runtime is not configured, and preservation of the Hermes tool-message contract with a test double. Python and embedded JavaScript syntax are also checked.


Live NVIDIA inference, Hermes execution with real credentials, microphone capture, local speaker output, and semantic-model download were not executed in this environment. The browser could not access the loopback preview, so rendered desktop/mobile and WebGL interaction QA remain unverified. This is a complete authored implementation with explicit external prerequisites, not a claim of production certification or hardware-qualified end-to-end operation.

## Design and technical sources

- [UI UX Pro Max](https://uupm.cc/): dark mode, glass surfaces, motion, and landing-page structure inspired the design direction. The style choice is design judgment, not an objective ranking.
- [Hermes AIAgent at the inspected revision](https://github.com/NousResearch/hermes-agent/blob/b7b35a84b7fbe1aa2e223a6ce726a2471300d0a4/run_agent.py): constructor integration.
- [Hermes turn facade](https://github.com/NousResearch/hermes-agent/blob/b7b35a84b7fbe1aa2e223a6ce726a2471300d0a4/agent/turn_facade.py): persistent conversation entry point.
- [NVIDIA Parakeet API](https://build.nvidia.com/nvidia/parakeet-1_1b-rnnt-multilingual-asr/api): hosted gRPC endpoint and function ID.
- [NVIDIA Riva client](https://github.com/nvidia-riva/python-clients): streaming PCM request/response contract.
- [NVIDIA local Parakeet deployment](https://docs.nvidia.com/nim/speech/latest/asr/deploy-asr-models/parakeet-rnnt.html): external GPU deployment requirements.
