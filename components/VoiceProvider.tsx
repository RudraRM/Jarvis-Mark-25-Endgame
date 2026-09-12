'use client';
import {createContext,useContext,useState,useRef,useEffect, useCallback, type ReactNode} from 'react';
import {recordingToWav} from '@/lib/audio';
type Status = 'idle'|'requesting'|'recording'|'transcribing';
type Voice = {chunks:Blob[];transcripts:string[];status:Status;error:string;start:()=>Promise<void>;stop:()=>void};
const Context = createContext<Voice|null>(null);
export const useVoice = () => {const value=useContext(Context);if(!value)throw Error('VoiceProvider required');return value;};
export function VoiceProvider({children}:{children:ReactNode}) {
  const [chunks,setChunks]=useState<Blob[]>([]),[transcripts,setTranscripts]=useState<string[]>([]),[status,setStatus]=useState<Status>('idle'),[error,setError]=useState('');
  const recorder=useRef<MediaRecorder|null>(null),stream=useRef<MediaStream|null>(null),timer=useRef<ReturnType<typeof setTimeout>|null>(null),busy=useRef(false),mounted=useRef(true),abort=useRef<AbortController|null>(null);
  const release=useCallback(()=>{stream.current?.getTracks().forEach(t=>t.stop());stream.current=null;if(timer.current)clearTimeout(timer.current);},[]);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;abort.current?.abort();if(recorder.current?.state==='recording')recorder.current.stop();release();};},[release]);
  const stop=()=>{if(recorder.current?.state==='recording')recorder.current.stop();};
  async function start(){
    if(busy.current)return;busy.current=true;setError('');setChunks([]);setStatus('requesting');
    try {
      if(!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder)throw Error('Microphone recording requires a supported browser on HTTPS or localhost.');
      const media=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});
      if(!mounted.current){media.getTracks().forEach(t=>t.stop());return;}stream.current=media;
      const mime=['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4'].find(m=>MediaRecorder.isTypeSupported(m));
      const recording=new MediaRecorder(media,mime?{mimeType:mime}:undefined);recorder.current=recording;const parts:Blob[]=[];
      recording.ondataavailable=e=>{if(e.data.size){parts.push(e.data);if(mounted.current)setChunks([...parts]);}};
      recording.onerror=()=>{setError('Microphone recording failed. Please retry.');release();busy.current=false;setStatus('idle');};
      recording.onstop=async()=>{
        release();if(!mounted.current)return;setStatus('transcribing');
        try {
          // Only finalized recordings are decoded: later MediaRecorder chunks are not standalone files.
          const wav=await recordingToWav(new Blob(parts,{type:recording.mimeType}));
          if(!mounted.current)return;const form=new FormData();form.set('file',wav,'speech.wav');
          abort.current=new AbortController();
          const response=await fetch('/api/voice/transcribe',{method:'POST',body:form,signal:abort.current.signal});const data=await response.json();
          if(!response.ok)throw Error(data.error ?? 'Transcription failed.');
          if(mounted.current){setTranscripts(previous=>[...previous.slice(-49),data.text]);console.info('[Jarvis ASR]',data.text);}
        }catch(e){if(mounted.current)setError(e instanceof Error?e.message:'Transcription failed.');}
        finally{busy.current=false;if(mounted.current)setStatus('idle');}
      };
      recording.start(250);setStatus('recording');timer.current=setTimeout(stop,15000);
    }catch(e){release();busy.current=false;if(mounted.current){setStatus('idle');setError(e instanceof Error?e.message:'Microphone unavailable.');}}
  }
  return <Context.Provider value={{chunks,transcripts,status,error,start,stop}}>{children}</Context.Provider>;
}
