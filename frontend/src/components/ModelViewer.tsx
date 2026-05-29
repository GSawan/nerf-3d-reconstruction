'use client';
import { Suspense, useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Bounds, Environment } from '@react-three/drei';
import { useLoader } from '@react-three/fiber';
import { PLYLoader } from 'three-stdlib';
import * as THREE from 'three';
import { EffectComposer, Bloom, Vignette } from '@react-three/postprocessing';

function GeometryLoader({ url }: { url: string }) {
  const geometry = useLoader(PLYLoader, url);
  
  // Normalization: Compute bounds, center, and uniform scale
  const { isMesh, scale } = useMemo(() => {
    geometry.computeBoundingBox();
    geometry.center();
    
    const bbox = geometry.boundingBox!;
    const size = new THREE.Vector3();
    bbox.getSize(size);
    const maxDim = Math.max(size.x, size.y, size.z);
    
    // Target size is exactly 2.0 units
    const scaleFactor = maxDim > 0 ? 2.0 / maxDim : 1.0;
    
    console.log("DEBUG: PLY Geometry Loaded!");
    console.log("DEBUG: Bounding Box Size:", size);
    console.log("DEBUG: Applied Scale:", scaleFactor);
    console.log("DEBUG: Point/Vertex Count:", geometry.attributes.position.count);
    
    // If geometry has an index, it means faces were generated (i.e. it's a mesh)
    const isMesh = geometry.index !== null;
    console.log("DEBUG: Is Mesh?", isMesh);
    
    // We compute vertex normals if it's a mesh so lighting works
    if (isMesh) {
      geometry.computeVertexNormals();
    }
    
    return { isMesh, scale: scaleFactor };
  }, [geometry]);

  // Render Mesh if we have faces, otherwise render Points
  if (isMesh) {
    return (
      <mesh geometry={geometry} scale={scale}>
        <meshStandardMaterial 
          vertexColors={geometry.hasAttribute('color')}
          roughness={0.6}
          metalness={0.2}
          side={THREE.DoubleSide}
        />
      </mesh>
    );
  } else {
    return (
      <points geometry={geometry} scale={scale}>
        <pointsMaterial 
          vertexColors={geometry.hasAttribute('color')}
          size={0.03} // Point clouds shouldn't be huge now that they are scaled to size 2.0
          sizeAttenuation={true} 
          transparent={true} 
          opacity={0.95}
        />
      </points>
    );
  }
}

interface ModelViewerProps {
  url: string;
}

export default function ModelViewer({ url }: ModelViewerProps) {
  return (
    <div className="relative w-full h-full bg-[#000000]">
      <div className="absolute top-4 left-6 z-10 pointer-events-none">
        <p className="text-xs font-mono font-bold tracking-[0.2em] text-[#00ffff]/70 uppercase drop-shadow-md">
          REAL-TIME 3D RECONSTRUCTION
        </p>
      </div>

      <Canvas 
        camera={{ position: [0, 0, 3], fov: 45 }}
        dpr={[1, 2]}
      >
        <color attach="background" args={['#000000']} />
        
        {/* Good lighting for meshes */}
        <ambientLight intensity={0.5} />
        <directionalLight position={[10, 10, 5]} intensity={1} />
        <directionalLight position={[-10, -10, -5]} intensity={0.5} />
        <Environment preset="city" />
        
        <Suspense fallback={
          <mesh>
            <sphereGeometry args={[0.5, 16, 16]} />
            <meshBasicMaterial color="#00ffff" wireframe />
          </mesh>
        }>
          <Bounds fit clip observe margin={1.2}>
            <GeometryLoader url={url} />
          </Bounds>
        </Suspense>
        
        <EffectComposer>
          <Bloom luminanceThreshold={0.8} mipmapBlur intensity={0.5} />
          <Vignette eskil={false} offset={0.1} darkness={1.1} />
        </EffectComposer>
        
        <OrbitControls 
          makeDefault 
          autoRotate={true}
          autoRotateSpeed={0.5}
          enableDamping={true} 
          dampingFactor={0.05} 
          minDistance={0.5}
          maxDistance={10}
        />
      </Canvas>
    </div>
  );
}
