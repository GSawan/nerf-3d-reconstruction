'use client';
/**
 * PLYViewer — renders a COLMAP sparse point cloud (.ply) using Three.js.
 * No external dependencies beyond what's already in package.json.
 * Supports: orbit controls, auto-center, point size control, color modes.
 */
import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

interface PLYViewerProps {
  modelUrl: string;
}

export default function PLYViewer({ modelUrl }: PLYViewerProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<{
    renderer: THREE.WebGLRenderer;
    scene: THREE.Scene;
    camera: THREE.PerspectiveCamera;
    controls: OrbitControls;
    animId: number;
  } | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pointCount, setPointCount] = useState(0);
  const [pointSize, setPointSize] = useState(2);
  const [colorMode, setColorMode] = useState<'vertex' | 'depth' | 'white'>('vertex');

  useEffect(() => {
    if (!mountRef.current) return;

    const container = mountRef.current;
    const W = container.clientWidth;
    const H = container.clientHeight;

    // ── Renderer ──
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setSize(W, H);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(new THREE.Color('#050505'), 1);
    container.appendChild(renderer.domElement);

    // ── Scene & Camera ──
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, W / H, 0.001, 1000);
    camera.position.set(0, 0, 3);

    // ── Controls ──
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.screenSpacePanning = false;
    controls.minDistance = 0.1;
    controls.maxDistance = 50;

    // ── Subtle Grid ──
    const grid = new THREE.GridHelper(10, 20, 0x222222, 0x111111);
    scene.add(grid);

    // ── Load PLY ──
    const loader = new PLYLoader();
    loader.load(
      modelUrl,
      (geometry) => {
        geometry.computeBoundingBox();
        geometry.computeBoundingSphere();

        const bbox = geometry.boundingBox!;
        const center = new THREE.Vector3();
        bbox.getCenter(center);
        geometry.translate(-center.x, -center.y, -center.z);

        // Scale to fit nicely
        const sphere = geometry.boundingSphere!;
        const scale = 2.0 / sphere.radius;
        geometry.scale(scale, scale, scale);

        // Point count
        const count = geometry.attributes.position.count;
        setPointCount(count);

        const hasVertexColors = !!(geometry.attributes.color);
        const material = new THREE.PointsMaterial({
          size: pointSize * 0.005,
          sizeAttenuation: true,
          vertexColors: hasVertexColors,
          // Always provide a valid color — when vertexColors=true, this acts as a multiplier (white = no tint)
          color: new THREE.Color(hasVertexColors ? '#ffffff' : '#88ccff'),
        });

        const points = new THREE.Points(geometry, material);
        points.name = 'model';
        scene.add(points);

        // Move camera to good viewpoint
        camera.position.set(0, 1, 3);
        controls.target.set(0, 0, 0);
        controls.update();

        // Grid position
        grid.position.y = -1;

        setLoading(false);
      },
      (xhr) => {
        // Progress — could be used for progress bar
      },
      (err) => {
        console.error('PLY load error:', err);
        setError('Failed to load 3D model. The PLY file may be missing or corrupted.');
        setLoading(false);
      }
    );

    // ── Animate ──
    let animId: number = 0;
    const animate = () => {
      animId = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    sceneRef.current = { renderer, scene, camera, controls, animId };

    // ── Resize ──
    const onResize = () => {
      if (!container) return;
      const w = container.clientWidth;
      const h = container.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener('resize', onResize);

    return () => {
      window.removeEventListener('resize', onResize);
      cancelAnimationFrame(animId);
      controls.dispose();
      renderer.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [modelUrl]);

  // Update point size live
  useEffect(() => {
    if (!sceneRef.current) return;
    const { scene } = sceneRef.current;
    const points = scene.getObjectByName('model') as THREE.Points;
    if (points && points.material instanceof THREE.PointsMaterial) {
      points.material.size = pointSize * 0.005;
      points.material.needsUpdate = true;
    }
  }, [pointSize]);

  // Update color mode live
  useEffect(() => {
    if (!sceneRef.current) return;
    const { scene } = sceneRef.current;
    const points = scene.getObjectByName('model') as THREE.Points;
    if (!(points && points.material instanceof THREE.PointsMaterial)) return;

    const geo = points.geometry;
    if (colorMode === 'vertex' && geo.attributes.color) {
      points.material.vertexColors = true;
      points.material.color.set('#ffffff');
    } else if (colorMode === 'depth') {
      points.material.vertexColors = false;
      points.material.color.set('#4488ff');
    } else {
      points.material.vertexColors = false;
      points.material.color.set('#ffffff');
    }
    points.material.needsUpdate = true;
  }, [colorMode]);

  return (
    <div className="relative w-full h-full bg-[#050505]">
      {/* Three.js canvas mount */}
      <div ref={mountRef} className="absolute inset-0" />

      {/* Loading overlay */}
      {loading && !error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#050505] z-10">
          <div className="w-10 h-10 border-2 border-white/10 border-t-emerald-400 rounded-full animate-spin mb-3" />
          <p className="text-[10px] text-emerald-400/60 tracking-widest animate-pulse">LOADING 3D MODEL...</p>
        </div>
      )}

      {/* Error overlay */}
      {error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#050505] z-10">
          <p className="text-red-400 text-xs mb-2 tracking-widest">LOAD ERROR</p>
          <p className="text-white/30 text-[10px] max-w-xs text-center">{error}</p>
        </div>
      )}

      {/* Controls overlay (bottom) */}
      {!loading && !error && (
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent px-4 py-3 flex items-center justify-between z-10">
          <div className="flex items-center gap-4">
            {/* Point size */}
            <div className="flex items-center gap-2">
              <label className="text-[9px] text-white/30 tracking-widest uppercase">Points</label>
              <input
                type="range"
                min="1"
                max="8"
                step="0.5"
                value={pointSize}
                onChange={(e) => setPointSize(Number(e.target.value))}
                className="w-20 h-0.5 accent-emerald-400"
              />
              <span className="text-[9px] text-white/30">{pointSize}</span>
            </div>

            {/* Color mode */}
            <div className="flex items-center gap-1.5">
              <label className="text-[9px] text-white/30 tracking-widest uppercase mr-1">Color</label>
              {(['vertex', 'depth', 'white'] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setColorMode(m)}
                  className={`text-[9px] px-2 py-0.5 border tracking-wider uppercase transition-colors ${
                    colorMode === m
                      ? 'border-emerald-500/50 text-emerald-400 bg-emerald-950/50'
                      : 'border-white/10 text-white/30 hover:border-white/20'
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>

          {/* Point count */}
          <div className="text-[9px] text-white/20 tracking-widest">
            {pointCount.toLocaleString()} POINTS
          </div>
        </div>
      )}
    </div>
  );
}
