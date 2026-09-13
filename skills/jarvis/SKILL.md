---
name: jarvis
description: Operate the local JARVIS voice gateway and blue holographic dashboard, interpret its telemetry, and diagnose microphone, Parakeet, memory, or local speech issues.
---

Use the JARVIS repository's README.md for installation and endpoint details. The gateway is launched from that repository with `python backend.py`; its homepage is http://127.0.0.1:8765. It runs basic chatbot replies through the configured NVIDIA model and upgrades to Hermes AIAgent tool-loop mode when HERMES_AGENT_PATH is configured.

The operator must enable microphone capture using the dashboard's Listen button. The microphone belongs to the machine running Python. Cloud ASR sends audio to NVIDIA; local NIM keeps ASR local. Local TTS playback belongs to that same machine.

The three-tier personality lives in prompt.txt. Only final conversational text is spoken. Preserve the runtime's existing approval boundaries and distinguish virtual telemetry from real hardware control. Never state that node dragging alters neural weights or security clearances.

For startup issues, check the dashboard's runtime feed and `/health`, then verify NVIDIA_API_KEY, optional HERMES_AGENT_PATH, RIVA_SERVER, and installed audio drivers. The site always connects to a real configured runtime and never substitutes simulated model responses.


Events are stored in data/events.sqlite3; conversation continuation is stored in the same database. Memory embeddings are computed locally when the configured sentence-transformers model loads. If it is unavailable, the dashboard exposes lexical retrieval status instead of claiming semantic recall. Stop the gateway before removing data to reset local history; Hermes keeps its own session data separately.
