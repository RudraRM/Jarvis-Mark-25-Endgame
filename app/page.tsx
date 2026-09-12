"use client";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { useAudio } from "@/components/AudioProvider";
import { ScrambleText } from "@/components/ScrambleText";
const ThreeCanvas=dynamic(()=>import("@/components/ThreeCanvas"),{ssr:false});

export default function Home(){
 const {recording,toggle,transcript}=useAudio(),[answer,setAnswer]=useState("Awaiting directive."),[logs,setLogs]=useState(["NEURAL CORE ONLINE","HERMES LINK STANDBY"]),[time,setTime]=useState("");
 useEffect(()=>{const id=setInterval(()=>setTime(new Date().toLocaleTimeString("en-GB")),1000);return()=>clearInterval(id)},[]);
 useEffect(()=>{if(!transcript)return; setLogs(x=>[...x.slice(-3),`VOICE / ${transcript}`]); (async()=>{const r=await fetch("/api/agent",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:transcript,history:[]})}); if(!r.body)return; const reader=r.body.getReader(), decoder=new TextDecoder(); let buffer="",out=""; while(true){const {done,value}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});const lines=buffer.split("\n");buffer=lines.pop()||"";for(const line of lines){try{const event=JSON.parse(line);if(event.type==="text"){out+=event.delta;setAnswer(out)}if(event.command)setLogs(x=>[...x.slice(-3),`EXEC / ${event.command.tool}:${event.command.value}`])}catch{}}}})()},[transcript]);
 const fullscreen=()=>document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen();
 return <main><div className="noise"/><header><div className="brand"><span className="mark">M85</span><div>JARVIS <b>MARK 85</b><small>NEURAL SYSTEM / ACTIVE</small></div></div><div className="status"><i/> SYSTEM ONLINE <span>{time}</span></div><div className="actions"><button onClick={fullscreen} aria-label="Toggle fullscreen">⛶ <span>FULLSCREEN</span></button><button className={recording?"mic active":"mic"} onClick={()=>toggle()} aria-pressed={recording}>◉ <span>{recording?"LISTENING":"VOICE LINK"}</span></button></div></header>
 <section className="hero"><div className="side left">ARC REACTOR<em>MK. LXXXV</em></div><ThreeCanvas/><div className="reticle r1"/><div className="reticle r2"/><div className="side right">POWER MATRIX<em>{recording?"SYNCHRONIZING":"NOMINAL"}</em></div></section>
 <section className="terminal"><div className="terminal-head"><span>HERMES // OPERATOR CHANNEL</span><span className="dots">•••</span></div><div className="log">{logs.map((l,i)=><div key={i}><b>0{i+1}</b>{l}</div>)}</div><ScrambleText text={answer}/><div className="hint">PRESS VOICE LINK · SPEAK A COMMAND · PRESS AGAIN TO TRANSMIT</div></section>
 <footer><span>85.00° N</span><div>STARK NEURAL INTERFACE <b>///</b> ENDGAME PROTOCOL</div><span>CORE // 100%</span></footer></main>
}
