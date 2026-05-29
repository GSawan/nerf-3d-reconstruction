'use client';
import { Suspense } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Splat, Bounds, Environment } from '@react-three/drei';
import { EffectComposer, Bloom, Vignette } from '@react-three/postprocessing';

interface GaussianViewerProps {
  splatUrl: string;
}

export default function GaussianViewer({ splatUrl }: GaussianViewerProps) {
  return (
    <div className="w-full h-full bg-black absolute inset-0 z-0">
      <Canvas
        gl={{ antialias: false }}
        camera={{ position: [0, 0, 5], fov: 45 }}
        dpr={[1, 2]}
      >
        <color attach="background" args={['#000000']} />
        <fog attach="fog" args={['#000000', 3, 10]} />
        <ambientLight intensity={0.2} />
        <Environment preset="city" />
        
        <Suspense
          fallback={
            <mesh>
              <sphereGeometry args={[0.5, 16, 16]} />
              <meshBasicMaterial color="#00ffff" wireframe />
            </mesh>
          }
        >
          <Bounds fit clip observe margin={1.0}>
            <Splat src={splatUrl} alphaTest={0.1} />
          </Bounds>
        </Suspense>
        
        <EffectComposer>
          <Bloom luminanceThreshold={0.5} mipmapBlur intensity={0.5} />
          <Vignette eskil={false} offset={0.1} darkness={1.1} />
        </EffectComposer>
        
        <OrbitControls
          makeDefault
          enableDamping
          dampingFactor={0.03}
          autoRotate
          autoRotateSpeed={0.3}
          maxDistance={10}
          minDistance={0.5}
        />
      </Canvas>
      
      {/* Label */}
      <div className="absolute top-8 left-8 z-10 font-mono text-xs tracking-widest text-[#00ffff] drop-shadow-[0_0_8px_rgba(0,255,255,0.8)] flex items-center gap-2">
        <div className="w-2 h-2 rounded-full bg-[#00ffff] animate-pulse" />
        REAL-TIME NEURAL RENDERING (3DGS)
      </div>
    </div>
  );
}
