"use client";

import { useId } from "react";

export type RoomAppearance = { background?: string; poster?: string; plant?: boolean; lamp?: boolean };

export default function RoomScene({ background = "default", poster, plant = false, lamp = false }: RoomAppearance) {
  const id = useId().replace(/:/g, "");
  const night = background === "night";
  const dawn = background === "dawn";
  const title = `Комната команды: ${night ? "ночной фон" : dawn ? "фон рассвет" : "базовый фон"}${poster ? ", постер" : ""}${plant ? ", монстера" : ""}${lamp ? ", лампа" : ""}`;
  return <svg viewBox="0 0 640 390" role="img" aria-labelledby={`${id}-title`} width="640" height="390">
    <title id={`${id}-title`}>{title}</title>
    <defs>
      <linearGradient id={`${id}-wall`} x2="0" y2="1"><stop stopColor={night ? "#2e3564" : dawn ? "#f6dece" : "#e9ecf8"} /><stop offset="1" stopColor={night ? "#515980" : dawn ? "#f6eee5" : "#f3f4fb"} /></linearGradient>
      <linearGradient id={`${id}-sky`} x2="0" y2="1"><stop stopColor={night ? "#1b2451" : dawn ? "#dfaebb" : "#bacaf0"} /><stop offset="1" stopColor={night ? "#6c70a3" : dawn ? "#f9d7a8" : "#e4eafa"} /></linearGradient>
      <radialGradient id={`${id}-light`}><stop stopColor="#ffdc89" stopOpacity=".55" /><stop offset="1" stopColor="#ffdc89" stopOpacity="0" /></radialGradient>
    </defs>
    <rect width="640" height="390" rx="20" fill={`url(#${id}-wall)`} />
    <path d="M0 280h640v90q0 20-20 20H20Q0 390 0 370Z" fill={night ? "#72748f" : "#deddef"} />
    <path d="M0 280h640M75 390l70-110m135 110 15-110m190 110-40-110" stroke={night ? "#9393aa" : "#ecebf6"} strokeWidth="2" />
    <rect x="61" y="38" width="169" height="196" rx="12" fill={night ? "#757b9e" : "#fff"} />
    <rect x="71" y="48" width="149" height="174" rx="6" fill={`url(#${id}-sky)`} />
    <circle cx={night ? "185" : "109"} cy="84" r="19" fill={night ? "#faf1ca" : "#fff2ce"} />
    {night && <><circle cx="193" cy="77" r="17" fill="#26315d" /><g fill="#e7eafa"><circle cx="97" cy="69" r="1.5" /><circle cx="141" cy="90" r="2" /><circle cx="200" cy="128" r="1.5" /><circle cx="114" cy="117" r="1.5" /></g></>}
    <path d="m71 186 32-37 39 20 38-41 40 40v54H71Z" fill={night ? "#6f799b" : "#a9b7db"} />
    <path d="m71 201 41-26 37 24 38-22 33 20v25H71Z" fill={night ? "#4d567d" : "#c6cfe6"} />
    <path d="M146 48v174M71 138h149" stroke={night ? "#757b9e" : "white"} strokeWidth="7" />
    <rect x="53" y="224" width="185" height="10" rx="4" fill={night ? "#999dbc" : "#fff"} />
    <ellipse cx="347" cy="332" rx="155" ry="30" fill={night ? "#595c7c" : "#c7c8e1"} />
    <path d="M299 266h184l-15 35H282Z" fill={night ? "#777aa8" : "#b6b7dd"} />
    <rect x="303" y="226" width="171" height="62" rx="17" fill={night ? "#8990bd" : "#bfc3e8"} />
    <rect x="278" y="255" width="35" height="51" rx="11" fill="#8e98cf" /><rect x="463" y="255" width="35" height="51" rx="11" fill="#8e98cf" />
    <rect x="310" y="276" width="158" height="30" rx="8" fill={night ? "#9a9fca" : "#cbd0ee"} />
    <rect x="326" y="242" width="38" height="31" rx="8" fill="#f5e0bf" transform="rotate(-9 345 257)" />
    <rect x="417" y="239" width="33" height="32" rx="8" fill="#697bc2" transform="rotate(8 434 255)" />
    <path d="M298 305v16m180-16v16" stroke="#5a5d84" strokeWidth="7" strokeLinecap="round" />
    <ellipse cx="323" cy="322" rx="59" ry="16" fill="#f9f7f1" /><path d="m281 326-5 27m87-27 5 27" stroke="#a59bae" strokeWidth="6" strokeLinecap="round" />
    <rect x="308" y="311" width="32" height="7" rx="2" fill="#5b6bc4" /><rect x="312" y="307" width="31" height="5" rx="2" fill="#ddd9f1" />
    <path d="M293 304h9v11h-9z" fill="#d2aa8e" /><path d="M301 306h3q5 4 0 7h-3" fill="none" stroke="#d2aa8e" strokeWidth="2" />
    <rect x="290" y="63" width="137" height="105" rx="5" fill={night ? "#727ba5" : "#d4d9ec"} />
    <rect x="297" y="70" width="123" height="91" rx="2" fill={poster === "orbit" ? "#252e61" : poster === "mountains" ? "#f3e9da" : night ? "#c0c5df" : "#f9fafe"} />
    {poster === "orbit" ? <><ellipse cx="358" cy="115" rx="43" ry="20" transform="rotate(-25 358 115)" fill="none" stroke="#d6c2f1" strokeWidth="2" /><circle cx="358" cy="115" r="22" fill="#8995df" /><circle cx="384" cy="92" r="5" fill="#f9d398" /><circle cx="322" cy="88" r="2" fill="#fff" /></> : poster === "mountains" ? <><circle cx="386" cy="92" r="11" fill="#ddb176" /><path d="m305 149 32-50 33 50Z" fill="#a2b4b0" /><path d="m340 149 34-62 38 62Z" fill="#6a878c" /><path d="m363 107 11-20 12 20-12-6Z" fill="#f2f2e6" /></> : <><path d="M333 128v-26l24-13 24 13v26l-24 13Z" fill="none" stroke="#aab4da" strokeWidth="3" /><path d="m344 115 9 9 17-20" fill="none" stroke="#8d9bce" strokeWidth="3" strokeLinecap="round" /></>}
    {plant && <g><ellipse cx="128" cy="315" rx="38" ry="11" fill={night ? "#525a78" : "#c7c8de"} /><path d="M111 275h39l-5 38h-29Z" fill="#cfaa90" /><path d="M130 277v-68m0 54-26-35m26 21 29-35" fill="none" stroke="#40796c" strokeWidth="4" /><path d="M126 236c-29-3-40-31-27-42 23-2 38 18 27 42Z" fill="#508b77" /><path d="M133 240c-3-30 23-52 38-43 6 24-15 46-38 43Z" fill="#689e82" /><path d="M129 215c-21-9-24-33-9-42 18 5 29 30 9 42Z" fill="#3f7669" /><path d="M100 200l17 24m45-19-21 24m-19-47 6 22" stroke="#bad0aa" strokeWidth="1.5" /></g>}
    {lamp && <g><circle cx="547" cy="176" r="77" fill={`url(#${id}-light)`} /><path d="M547 184v125" stroke={night ? "#d1bf9e" : "#b7a083"} strokeWidth="5" /><ellipse cx="547" cy="313" rx="26" ry="6" fill="#a299a6" /><path d="m524 139-16 47h78l-17-47Z" fill="#f4dfb5" /><ellipse cx="547" cy="186" rx="39" ry="6" fill="#ffe8ad" /></g>}
    <g fill={night ? "#979bc0" : "#b8c0dd"}><circle cx="477" cy="79" r="2" /><path d="m504 115 2-6 2 6 6 2-6 2-2 6-2-6-6-2Z" /></g>
  </svg>;
}
