import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  const key = process.env.NVIDIA_API_KEY;
  if (!key) return NextResponse.json({ error: "NVIDIA_API_KEY is not configured" }, { status: 503 });
  const incoming = await request.formData();
  const audio = incoming.get("audio");
  if (!(audio instanceof Blob)) return NextResponse.json({ error: "An audio file is required" }, { status: 400 });
  const body = new FormData();
  body.append("file", audio, "speech.webm");
  body.append("model", "nvidia/parakeet-ctc-1.1b-asr");
  body.append("language", "en");
  const response = await fetch(process.env.NVIDIA_ASR_ENDPOINT || "https://integrate.api.nvidia.com/v1/audio/transcriptions", {
    method: "POST", headers: { Authorization: `Bearer ${key}` }, body,
  });
  if (!response.ok) return NextResponse.json({ error: `Transcription failed (${response.status})` }, { status: 502 });
  const result = await response.json();
  return NextResponse.json({ text: result.text || result.transcript || "" });
}
