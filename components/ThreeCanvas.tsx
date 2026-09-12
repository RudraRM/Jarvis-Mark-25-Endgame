"use client";
import { Canvas, useFrame } from "@react-three/fiber";
import { Float, OrbitControls, Stars } from "@react-three/drei";
import { useRef, useState } from "react";
import * as THREE from "three";
import { useAudio } from "./AudioProvider";

const rings = Array.from({ length: 9 }, (_, i) => ({ radius: 1.15 + i * .15, tube: i % 3 === 0 ? .012 : .005 }));
function Reactor({ rotation, zoom }: { rotation: [number, number]; zoom: number }) {
  const group = useRef<THREE.Group>(null), { level } = useAudio();
  useFrame((_, delta) => { if (!group.current) return; group.current.rotation.z += delta * (.045 + level * .7); const s = zoom * (1 + level * .11); group.current.scale.lerp(new THREE.Vector3(s,s,s), .1); });
  return <Float speed={1.2} rotationIntensity={.12} floatIntensity={.18}><group ref={group} rotation={[rotation[0], rotation[1], 0]}>
    {rings.map((r, i) => <mesh key={i} rotation={[i % 2 ? Math.PI / 2 : 0, i % 3 ? .15 : Math.PI / 2, i * .18]}><torusGeometry args={[r.radius, r.tube, 8, 128]} /><meshBasicMaterial color={i % 3 ? "#61e7ff" : "#e9fbff"} transparent opacity={.72} /></mesh>)}
    {Array.from({length: 24},(_,i)=><mesh key={`s${i}`} rotation={[0,0,(i/24)*Math.PI*2]}><boxGeometry args={[.035,1.98,.018]}/><meshBasicMaterial color="#47d9ff" transparent opacity={.28}/></mesh>)}
    <mesh><icosahedronGeometry args={[.72,2]}/><meshBasicMaterial color="#69edff" wireframe transparent opacity={.48}/></mesh>
    <pointLight color="#28d9ff" intensity={10 + level * 25} distance={8}/>
  </group></Float>;
}
export default function ThreeCanvas() {
  const [rotation,setRotation]=useState<[number,number]>([0,0]), [zoom,setZoom]=useState(1);
  const key=(e:React.KeyboardEvent)=>{ const d=.12; if(["ArrowUp","w","W"].includes(e.key)) setRotation(([x,y])=>[x-d,y]); if(["ArrowDown","s","S"].includes(e.key)) setRotation(([x,y])=>[x+d,y]); if(["ArrowLeft","a","A"].includes(e.key)) setRotation(([x,y])=>[x,y-d]); if(["ArrowRight","d","D"].includes(e.key)) setRotation(([x,y])=>[x,y+d]); if(e.key==="+") setZoom(z=>Math.min(1.5,z+.1)); if(e.key==="-") setZoom(z=>Math.max(.6,z-.1)); };
  return <div className="canvas" tabIndex={0} role="application" aria-label="Interactive Mark 85 arc reactor. Use WASD or arrow keys to rotate, plus and minus to scale." onKeyDown={key}>
    <Canvas camera={{position:[0,0,5.5],fov:42}} gl={{antialias:true,alpha:true}}><ambientLight intensity={.3}/><Stars radius={40} depth={20} count={650} factor={1.5} fade speed={.3}/><Reactor rotation={rotation} zoom={zoom}/><OrbitControls enablePan={false} enableZoom={false} enableDamping dampingFactor={0.05}/></Canvas>
    <span className="sr-only" aria-live="polite">Reactor rotation {rotation[0].toFixed(1)}, {rotation[1].toFixed(1)}; scale {zoom.toFixed(1)}.</span>
  </div>;
}
