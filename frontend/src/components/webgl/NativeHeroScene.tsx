'use client';
import { useRef, useMemo } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';
import * as THREE from 'three';
import { EffectComposer, Vignette, Noise } from '@react-three/postprocessing';

function Model() {
  const { scene } = useGLTF('/roman_bust.glb');
  const groupRef = useRef<THREE.Group>(null);
  
  // Clean, graphic matte obsidian material (No shaders, no glitches)
  const material = useMemo(() => {
    return new THREE.MeshPhysicalMaterial({
      color: '#080808', // Matte obsidian
      roughness: 0.68,
      metalness: 0.05,
      envMapIntensity: 0.15,
      clearcoat: 0.0, 
      side: THREE.DoubleSide
    });
  }, []);

  const clonedScene = useMemo(() => {
    const clone = scene.clone();
    clone.traverse((child) => {
      if ((child as THREE.Mesh).isMesh) {
        const mesh = child as THREE.Mesh;
        mesh.material = material;
      }
    });
    return clone;
  }, [scene, material]);

  useFrame((state) => {
    if (groupRef.current) {
      // Reverted to internal clock for buttery-smooth performance
      // Speed increased by 30% (0.05 -> 0.065)
      groupRef.current.rotation.y = state.clock.elapsedTime * 0.065; 
    }
  });

  return (
    <group ref={groupRef} position={[0, -1.0, 0]} rotation={[0, -0.2, 0]}>
      <primitive object={clonedScene} scale={2.25} />
    </group>
  );
}

useGLTF.preload('/roman_bust.glb');

export default function NativeHeroScene({ hideStatue = false }: { hideStatue?: boolean }) {
  return (
    <div className="absolute inset-0 z-20 pointer-events-none">
      <Canvas camera={{ position: [0, 0, 4.5], fov: 45 }} gl={{ antialias: true, alpha: true }}>
        {!hideStatue && (
          <>
            {/* Minimal Editorial Lighting */}
            <ambientLight intensity={0.3} />
            {/* One soft top-left light */}
            <directionalLight position={[-5, 5, 2]} intensity={2.0} color="#ffffff" />
            {/* One subtle rim light */}
            <directionalLight position={[5, -2, -5]} intensity={1.0} color="#ffffff" />
            
            <Model />
          </>
        )}
        
        {/* Restrained Postprocessing */}
        <EffectComposer disableNormalPass multisampling={4}>
          <Noise opacity={0.025} />
          <Vignette eskil={false} offset={0.1} darkness={0.8} />
        </EffectComposer>
      </Canvas>
    </div>
  );
}
