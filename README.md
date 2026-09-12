# Jarvis Mark 85

## Status
Phase 1 implementation checkpoint. **Not a finished application.** Phases 2–4 have not started because the requested live-speech verification gate has not passed. No final pull request has been opened.

## Run
Use Node.js 22 or newer. Run `npm ci`, copy `.env.example` to `.env.local`, and set `NVIDIA_API_KEY` there (never commit it). Run `npm run dev`, open http://localhost:3000, allow microphone access, record a phrase, then select **Stop & transcribe**. Compare the spoken phrase against the displayed transcript and browser console `[Jarvis ASR]` entry. Repeat with several phrases and microphone permission denied.

## Implemented
- MediaRecorder emits chunks into shared React Context every 250 ms.
- Finalized recordings are decoded, downmixed and resampled to 16 kHz mono PCM WAV.
- Server-only Parakeet NVCF integration with byte limits, WAV validation, timeout, cross-origin rejection and sanitized errors.
- Transcript history array, recording cleanup, maximum 15-second recording, accessible test interface.

This checkpoint uses utterance-based transcription after stopping, not continuous live text. Continuous segmentation/streaming and browser recording compatibility must be validated before closing Phase 1. No simulated result is presented as actual speech recognition.

## Verification
`npm test`: PCM encoding and API contract/error tests using a mocked NVIDIA response.
`npm run typecheck`: TypeScript check.
`npm run build`: Next.js production build.

Live provider accuracy, actual browser microphone/decode behavior, and continuous transcription are **unverified**. NVIDIA_API_KEY was absent in the implementation environment. This is a local development checkpoint; add authentication and deployment-level rate limits before exposing a paid provider route publicly.

## References
- https://build.nvidia.com/nvidia/parakeet-ctc-1_1b-asr/api
- https://build.nvidia.com/google/diffusiongemma-26b-a4b-it
- https://uupm.cc/

The Parakeet model is selected by its dedicated function endpoint, not by posting to nvidia.com. The remaining planned phases are Hermes orchestration, an interactive accessible Three.js reactor, and the minimal audio-reactive HUD.
