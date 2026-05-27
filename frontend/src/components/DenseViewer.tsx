'use client';
import { Suspense, useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Bounds } from '@react-three/drei';
import { useLoader } from '@react-three/fiber';
import { PLYLoader } from 'three-stdlib';
import * as THREE from 'three';

function GeometryLoader({ url }: { url: string }) {
  const geometry = useLoader(PLYLoader, url);
  
  const isMesh = useMemo(() => {
    // Poisson mesher generates indexed geometry (faces)
    return geometry.index !== null;
  }, [geometry]);

  // Center geometry perfectly
  useMemo(() => {
    geometry.computeBoundingBox();
    geometry.center();
    if (isMesh) {
      geometry.computeVertexNormals();
    }
  }, [geometry, isMesh]);

  if (isMesh) {
    return (
      <mesh geometry={geometry}>
        <meshStandardMaterial 
          color="#cccccc" 
          metalness={0.2} 
          roughness={0.7} 
          side={THREE.DoubleSide}
        />
      </mesh>
    );
  }

  // Fallback to Point Cloud
  return (
    <points geometry={geometry}>
      <pointsMaterial 
        size={0.07} 
        color="#00ffff" 
        sizeAttenuation={true} 
        transparent={true} 
        opacity={0.8}
        blending={THREE.AdditiveBlending}
        depthWrite={false}
      />
    </points>
  );
}

interface DenseViewerProps {
  url: string;
}

export default function DenseViewer({ url }: DenseViewerProps) {
  // Extract filename for label
  const filename = url.split('/').pop() || 'Model';
  const label = filename.includes('meshed-poisson') 
    ? 'DENSE POISSON MESH' 
    : filename.includes('fused') 
    ? 'DENSE FUSED POINT CLOUD' 
    : 'SPARSE POINT CLOUD';

  return (
    <div className="relative w-full h-full bg-[#050505]">
      <div className="absolute top-4 left-6 z-10 pointer-events-none">
        <p className="text-xs font-mono font-bold tracking-[0.2em] text-[#00ffff]/70 uppercase drop-shadow-md">
          {label}
        </p>
      </div>

      <Canvas camera={{ position: [0, 0, 3], fov: 45 }}>
        <color attach="background" args={['#050505']} />
        
        <ambientLight intensity={0.4} />
        <directionalLight position={[10, 10, 5]} intensity={1.5} />
        <directionalLight position={[-10, -10, -5]} intensity={0.5} />
        
        <Suspense fallback={null}>
          <Bounds fit clip observe margin={1.0}>
            <GeometryLoader url={url} />
          </Bounds>
        </Suspense>
        
        <OrbitControls 
          makeDefault 
          autoRotate={true}
          autoRotateSpeed={0.8}
          enableDamping={true} 
          dampingFactor={0.05} 
          minDistance={0.5}
          maxDistance={8}
        />
      </Canvas>
    </div>
  );
}
