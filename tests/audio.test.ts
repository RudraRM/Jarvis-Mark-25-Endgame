import {test} from 'node:test';import assert from 'node:assert/strict';import {pcmWav} from '../lib/audio';import {POST} from '../app/api/voice/transcribe/route';
test('WAV encodes mono PCM with clipping and accurate sizes',()=>{const v=new DataView(pcmWav(new Float32Array([-2,0,2])));assert.equal(v.byteLength,50);assert.equal(v.getUint32(24,true),16000);assert.equal(v.getUint16(22,true),1);assert.equal(v.getInt16(44,true),-32768);assert.equal(v.getInt16(48,true),32767);assert.equal(v.getUint32(40,true),6);});
test('route rejects cross-origin, missing key and invalid audio; forwards valid WAV securely',async()=>{
 const old=process.env.NVIDIA_API_KEY;const original=globalThis.fetch;
 try {
 delete process.env.NVIDIA_API_KEY;
 assert.equal((await POST(new Request('http://localhost/api/voice/transcribe',{method:'POST',headers:{origin:'https://evil.example'}}))).status,403);
 assert.equal((await POST(new Request('http://localhost/api/voice/transcribe',{method:'POST'}))).status,503);
 process.env.NVIDIA_API_KEY='test-only';
 const request=(blob:Blob)=>{const form=new FormData();form.set('file',blob,'speech.wav');return new Request('http://localhost/api/voice/transcribe',{method:'POST',body:form});};
 assert.equal((await POST(request(new Blob(['bad'])))).status,400);
 let called=false;globalThis.fetch=async(url,options)=>{called=true;assert.match(String(url),/invocation.api.nvcf.nvidia.com/);assert.equal((options?.headers as Record<string,string>).Authorization,'Bearer test-only');assert.equal((options?.body as FormData).get('language'),'en-US');return Response.json({text:'activate hyper-rotation'});};
 const result=await POST(request(new Blob([pcmWav(new Float32Array(16000))])));assert.equal(result.status,200);assert.deepEqual(await result.json(),{text:'activate hyper-rotation'});assert.ok(called);
 globalThis.fetch=async()=>new Response('',{status:401});assert.equal((await POST(request(new Blob([pcmWav(new Float32Array(10))])))).status,502);
 }finally{globalThis.fetch=original;if(old===undefined)delete process.env.NVIDIA_API_KEY;else process.env.NVIDIA_API_KEY=old;}
});
