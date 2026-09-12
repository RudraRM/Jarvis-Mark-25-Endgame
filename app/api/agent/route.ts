import { NextRequest } from "next/server";

type Message = { role: "user" | "assistant"; content: string };
const directive = "You are HERMES, the concise operations intelligence for Jarvis Mark 85. Reply in short cinematic system blocks. Never claim a web action succeeded unless a tool command is present.";

function commandFor(text: string) {
  const s = text.toLowerCase();
  if (s.includes("hyper-rotation")) return { tool: "rotation", value: "hyper" };
  if (s.includes("system diagnostic")) return { tool: "diagnostic", value: "run" };
  const color = s.match(/change color to (ruby|cyan|gold|violet)/)?.[1];
  return color ? { tool: "color", value: color } : null;
}

export async function POST(request: NextRequest) {
  const { text, history = [] } = (await request.json()) as { text: string; history?: Message[] };
  const command = commandFor(text || "");
  const key = process.env.NVIDIA_API_KEY;
  if (!key) {
    const message = command ? `Command recognized. ${command.tool} protocol set to ${command.value}.` : "HERMES link ready. Configure NVIDIA_API_KEY to enable intelligence streaming.";
    return new Response(`${JSON.stringify({ type: "command", command })}\n${JSON.stringify({ type: "text", delta: message })}\n`, { headers: { "Content-Type": "application/x-ndjson" } });
  }
  const upstream = await fetch(process.env.NVIDIA_LLM_ENDPOINT || "https://integrate.api.nvidia.com/v1/chat/completions", {
    method: "POST", headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify({ model: "google/diffusiongemma-26b-a4b-it", messages: [{ role: "system", content: directive }, ...history.slice(-8), { role: "user", content: text }], stream: true }),
  });
  if (!upstream.ok || !upstream.body) return new Response(JSON.stringify({ error: `Agent upstream failed (${upstream.status})` }), { status: 502 });
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  const stream = new ReadableStream({ async start(controller) {
    controller.enqueue(encoder.encode(`${JSON.stringify({ type: "command", command })}\n`));
    const reader = upstream.body!.getReader(); let buffer = "";
    while (true) { const { done, value } = await reader.read(); if (done) break; buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n"); buffer = lines.pop() || "";
      for (const line of lines) { if (!line.startsWith("data: ") || line.includes("[DONE]")) continue; try { const delta = JSON.parse(line.slice(6)).choices?.[0]?.delta?.content; if (delta) controller.enqueue(encoder.encode(`${JSON.stringify({ type: "text", delta })}\n`)); } catch {} }
    } controller.close();
  }});
  return new Response(stream, { headers: { "Content-Type": "application/x-ndjson", "Cache-Control": "no-cache" } });
}
