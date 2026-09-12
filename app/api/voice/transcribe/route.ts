export const runtime = 'nodejs';
const ENDPOINT = 'https://1598d209-5e27-4d3c-8079-4751568b1081.invocation.api.nvcf.nvidia.com/v1/audio/transcriptions';
const MAX_BYTES = 1024 * 1024;
export async function POST(request: Request) {
  const origin = request.headers.get('origin');
  if (origin && origin !== new URL(request.url).origin) return Response.json({error:'Cross-origin request rejected.'}, {status:403});
  if (!process.env.NVIDIA_API_KEY) return Response.json({error:'Set NVIDIA_API_KEY on the server to enable transcription.'}, {status:503});
  try {
    // Bound bytes before multipart parsing, even without Content-Length.
    const reader = request.body?.getReader(); if (!reader) return Response.json({error:'Audio required.'}, {status:400});
    const chunks: Uint8Array[] = []; let size = 0;
    while (true) { const {done,value} = await reader.read(); if (done) break; size += value.length;
      if (size > MAX_BYTES) { await reader.cancel(); return Response.json({error:'Recording too large.'}, {status:413}); } chunks.push(value); }
    const body = new Uint8Array(size); let offset = 0; for (const chunk of chunks) {body.set(chunk,offset);offset+=chunk.length;}
    const form = await new Response(body, {headers:{'Content-Type':request.headers.get('content-type') ?? ''}}).formData();
    const file = form.get('file');
    if (!(file instanceof File) || file.size < 46) return Response.json({error:'A PCM WAV recording is required.'}, {status:400});
    const bytes = await file.arrayBuffer(); const v = new DataView(bytes); const text = new TextDecoder();
    if (text.decode(bytes.slice(0,4)) !== 'RIFF' || text.decode(bytes.slice(8,12)) !== 'WAVE' || text.decode(bytes.slice(12,16)) !== 'fmt ' || v.getUint32(16,true)!==16 || v.getUint16(20,true)!==1 || v.getUint16(22,true)!==1 || v.getUint32(24,true)!==16000 || v.getUint16(34,true)!==16 || text.decode(bytes.slice(36,40))!=='data' || v.getUint32(40,true)!==bytes.byteLength-44)
      return Response.json({error:'Expected 16 kHz mono 16-bit PCM WAV.'}, {status:400});
    const upstream = new FormData(); upstream.set('file',file,'speech.wav'); upstream.set('language','en-US'); upstream.set('word_time_offsets','True');
    // The dedicated NVCF function selects parakeet-ctc-1.1b-asr.
    const response = await fetch(ENDPOINT,{method:'POST',headers:{Authorization:`Bearer ${process.env.NVIDIA_API_KEY}`},body:upstream,signal:AbortSignal.any([request.signal,AbortSignal.timeout(30000)])});
    if (!response.ok) return Response.json({error:`Transcription provider returned ${response.status}.`},{status:502});
    const data = await response.json();
    if (typeof data.text !== 'string') return Response.json({error:'Invalid transcription response.'},{status:502});
    return Response.json({text:data.text},{headers:{'Cache-Control':'no-store'}});
  } catch { return Response.json({error:'Transcription failed. Check the recording and retry.'},{status:502}); }
}
