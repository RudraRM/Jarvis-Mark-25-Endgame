"use client";
import { motion } from "framer-motion";
import { useEffect, useState } from "react";
const glyphs="01<>/{}[]ΞΔΦ";
export function ScrambleText({ text }: { text: string }) { const [shown,setShown]=useState(""); useEffect(()=>{let tick=0; const id=setInterval(()=>{tick++; setShown(text.split("").map((c,i)=>i<tick/2?c:c===" "?" ":glyphs[Math.floor(Math.random()*glyphs.length)]).join("")); if(tick>=text.length*2)clearInterval(id)},24); return()=>clearInterval(id)},[text]); return <motion.p initial={{opacity:0}} animate={{opacity:1}} className="response">{shown}</motion.p> }
