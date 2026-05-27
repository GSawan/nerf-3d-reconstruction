'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import NativeHeroScene from '@/components/webgl/NativeHeroScene';

const MarqueeText = () => (
  <div 
    className="absolute top-[54.5%] left-0 w-full flex items-center pointer-events-none overflow-hidden -translate-y-1/2"
  >
    <style>{`
        @keyframes marquee {
          0% { transform: translate3d(0%, 0, 0); }
          100% { transform: translate3d(-50%, 0, 0); }
        }
        .animate-marquee {
          display: flex;
          width: 200%;
          animation: marquee 22.5s linear infinite;
          will-change: transform;
          backface-visibility: hidden;
          perspective: 1000px;
        }
      `}</style>
    <div className="animate-marquee whitespace-nowrap">
      <h1 
        className="text-[15.4vw] font-normal tracking-tighter text-[#25250F] opacity-100 select-none mix-blend-color-burn px-8" 
        style={{ fontFamily: 'var(--font-outfit)' }}
      >
        Just NeRF It Dude !
      </h1>
      <h1 
        className="text-[15.4vw] font-normal tracking-tighter text-[#25250F] opacity-100 select-none mix-blend-color-burn px-8" 
        style={{ fontFamily: 'var(--font-outfit)' }}
      >
        Just NeRF It Dude !
      </h1>
    </div>
  </div>
);

export default function Home() {
  return (
    <main className="relative w-full h-screen overflow-hidden bg-[#c8c8b6] selection:bg-zinc-800 selection:text-[#c8c8b6]">
      
      {/* ================= LAYER 1: BASE NORMAL PAGE ================= */}
      <div className="absolute inset-0 z-10 pointer-events-none">
        <MarqueeText />
      </div>

      {/* ================= LAYER 3: STATUE ================= */}
      {/* The statue is drawn ON TOP of the magnifier box so it remains unzoomed and mathematically flawless */}
      <div className="absolute inset-0 z-30 pointer-events-none">
        <NativeHeroScene />
      </div>

      {/* ================= FOREGROUND UI ================= */}
      <div className="absolute inset-0 z-40 pointer-events-none">
        <div 
          className="absolute text-[#111111] leading-[0.835] text-[3.2vw] tracking-tight flex flex-col items-start" 
          style={{ fontFamily: '"Overused Grotesk", sans-serif', right: '4%', top: '5%' }}
        >
          <span>Neo3D?</span>
          <span className="ml-[1.5em]">Yup!</span>
        </div>

        {/* Bottom Centered Group */}
        <div className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-6 pointer-events-auto w-full">
          {/* IMAGE RECONSTRUCTION */}
          <h2 
            className="text-[#111111] text-[3.6vw] leading-[0.812] uppercase" 
            style={{ fontFamily: 'var(--font-bungee)' }}
          >
            IMAGE RECONSTRUCTION
          </h2>
            
          {/* Button */}
          <Link href="/upload" className="group">
            <button className="px-8 py-3 rounded-full border border-[#111111] text-[#111111] text-xs font-semibold tracking-[0.2em] uppercase hover:bg-[#111111] hover:text-[#c8c8b6] transition-colors duration-500 bg-[#c8c8b6]/50 backdrop-blur-sm" style={{ fontFamily: 'var(--font-outfit)' }}>
              Neo3D iT !
            </button>
          </Link>
        </div>
      </div>

      {/* 4. BLUE NOISE DITHER OVERLAY (z-index 50) */}
      {/* Drastically increased opacity so the grain is highly visible */}
      <div 
        className="absolute inset-0 z-50 opacity-[0.65] pointer-events-none mix-blend-multiply"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='blueNoise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='1' stitchTiles='stitch'/%3E%3CfeComponentTransfer%3E%3CfeFuncA type='discrete' tableValues='0 1'/%3E%3C/feComponentTransfer%3E%3CfeColorMatrix type='matrix' values='1 0 0 0 0, 0 1 0 0 0, 0 0 1 0 0, 0 0 0 0.8 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23blueNoise)'/%3E%3C/svg%3E")`,
          backgroundRepeat: 'repeat',
          backgroundSize: '128px 128px'
        }}
      />
    </main>
  );
}
