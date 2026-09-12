"use client";
import { createContext, ReactNode, useCallback, useContext, useRef, useState } from "react";

type AudioState = { recording: boolean; level: number; transcript: string; toggle: () => Promise<void> };
const AudioContextState = createContext<AudioState>({ recording: false, level: 0, transcript: "", toggle: async () => {} });
export const useAudio = () => useContext(AudioContextState);

export function AudioProvider({ children }: { children: ReactNode }) {
  const [recording, setRecording] = useState(false), [level, setLevel] = useState(0), [transcript, setTranscript] = useState("");
  const recorder = useRef<MediaRecorder | null>(null), frame = useRef(0);
  const toggle = useCallback(async () => {
    if (recorder.current?.state === "recording") { recorder.current.stop(); setRecording(false); cancelAnimationFrame(frame.current); return; }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    const media = new MediaRecorder(stream), chunks: Blob[] = [];
    const context = new window.AudioContext(), analyser = context.createAnalyser(); analyser.fftSize = 256;
    context.createMediaStreamSource(stream).connect(analyser); const data = new Uint8Array(analyser.frequencyBinCount);
    const sample = () => { analyser.getByteFrequencyData(data); setLevel(data.reduce((a, b) => a + b, 0) / data.length / 255); frame.current = requestAnimationFrame(sample); }; sample();
    media.ondataavailable = ({ data }) => data.size && chunks.push(data);
    media.onstop = async () => { stream.getTracks().forEach(t => t.stop()); await context.close(); setLevel(0); const body = new FormData(); body.append("audio", new Blob(chunks, { type: media.mimeType }));
      try { const response = await fetch("/api/voice/transcribe", { method: "POST", body }); const result = await response.json(); if (!response.ok) throw new Error(result.error); setTranscript(result.text); console.info("[MARK-85 ASR]", result.text); } catch (error) { console.error("[MARK-85 ASR]", error); }
    };
    recorder.current = media; media.start(250); setRecording(true);
  }, []);
  return <AudioContextState.Provider value={{ recording, level, transcript, toggle }}>{children}</AudioContextState.Provider>;
}
