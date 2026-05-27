'use client';
import { useState, useRef } from 'react';
import { useNeRFStore } from '@/store/nerfStore';
import { NeRFApi } from '@/lib/api';
import { useRouter } from 'next/navigation';

export default function UploadDashboard() {
  const router = useRouter();
  const setSession = useNeRFStore(s => s.setSession);
  const setError = useNeRFStore(s => s.setError);
  const globalError = useNeRFStore(s => s.globalError);
  const reconstructionMode = useNeRFStore(s => s.reconstructionMode);
  const setReconstructionMode = useNeRFStore(s => s.setReconstructionMode);
  
  const [files, setFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const droppedFiles = Array.from(e.dataTransfer.files).filter(f => f.type === 'image/jpeg' || f.type === 'image/png');
      setFiles(prev => [...prev, ...droppedFiles]);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      const selectedFiles = Array.from(e.target.files).filter(f => f.type === 'image/jpeg' || f.type === 'image/png');
      setFiles(prev => [...prev, ...selectedFiles]);
    }
  };

  const removeFile = (index: number) => {
    setFiles(files.filter((_, i) => i !== index));
  };

  const handleUpload = async () => {
    if (files.length < 10) {
      setError("A minimum of 10 images is required for reconstruction.");
      return;
    }
    if (reconstructionMode === "ngp" && files.length > 60) {
      setError("NGP Mode has a hard limit of 60 images to prevent VRAM overflow. Please use Mesh mode for larger datasets.");
      return;
    }
    
    setIsUploading(true);
    setError(null);
    
    try {
      const session = await NeRFApi.uploadDataset(files);
      setSession(session);
      // Once uploaded and preprocessed, move to viewer/processing queue
      router.push('/viewer');
    } catch (err: any) {
      console.error(err);
      setError(err?.response?.data?.detail || err.message);
    } finally {
      setIsUploading(false);
    }
  };
  
  return (
     <div className="flex-1 flex flex-col items-center justify-center p-8 min-h-screen bg-[#0a0a0a] text-[#e2e0d8] selection:bg-[#25250F] selection:text-[#e2e0d8]">
       <div className="w-full max-w-4xl space-y-8">
         <div className="space-y-2">
           <h1 className="text-4xl font-light tracking-tight uppercase" style={{ fontFamily: '"Overused Grotesk", sans-serif' }}>Data Ingestion</h1>
           <p className="text-[#e2e0d8]/50 text-sm" style={{ fontFamily: 'var(--font-outfit)' }}>Upload raw captures to begin the neural reconstruction pipeline. Minimum 10 images required. Jpeg/Png.</p>
         </div>
         
         {globalError && (
           <div className="p-4 bg-red-950/30 text-red-400 text-sm rounded-none border border-red-900/50" style={{ fontFamily: 'var(--font-outfit)' }}>
             {globalError}
           </div>
         )}
         
         {/* DRAG AND DROP ZONE */}
         <div 
           className={`relative border border-dashed transition-all duration-300 ease-in-out p-12 text-center flex flex-col items-center justify-center gap-4 cursor-pointer min-h-[300px] ${dragActive ? 'border-[#e2e0d8] bg-[#e2e0d8]/5' : 'border-[#e2e0d8]/20 hover:border-[#e2e0d8]/50 bg-black/20'}`}
           onDragEnter={handleDrag}
           onDragLeave={handleDrag}
           onDragOver={handleDrag}
           onDrop={handleDrop}
           onClick={() => fileInputRef.current?.click()}
         >
           <input 
             ref={fileInputRef}
             type="file" 
             multiple 
             accept="image/jpeg, image/png"
             onChange={handleChange} 
             className="hidden"
           />
           <div className="w-12 h-12 rounded-full bg-[#e2e0d8]/10 flex items-center justify-center mb-2">
             <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-[#e2e0d8]">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
             </svg>
           </div>
           <p className="text-lg font-light tracking-wide">Drag & drop captures here</p>
           <p className="text-sm text-[#e2e0d8]/40">or click to browse local storage</p>
         </div>

         {/* PREVIEW GRID */}
         {files.length > 0 && (
           <div className="space-y-4">
             <div className="flex justify-between items-center text-sm font-semibold tracking-widest uppercase text-[#e2e0d8]/60" style={{ fontFamily: 'var(--font-outfit)' }}>
               <span>Queue ({files.length} items)</span>
               <button onClick={() => setFiles([])} className="hover:text-white transition-colors">Clear All</button>
             </div>
             <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 gap-4 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
               {files.map((f, i) => (
                 <div key={i} className="relative group aspect-square bg-[#111] border border-[#e2e0d8]/10 overflow-hidden">
                   <img src={URL.createObjectURL(f)} alt="preview" className="w-full h-full object-cover opacity-80 group-hover:opacity-100 group-hover:scale-105 transition-all duration-500" />
                   <button 
                     onClick={(e) => { e.stopPropagation(); removeFile(i); }} 
                     className="absolute top-1 right-1 w-6 h-6 bg-black/80 text-white opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-xs"
                   >
                     ✕
                   </button>
                 </div>
               ))}
             </div>
           </div>
         )}
         
         <div className="pt-4 border-t border-[#e2e0d8]/10 space-y-6">
           <div className="flex items-center justify-between p-4 bg-[#111] border border-white/5">
             <div className="space-y-1">
               <h3 className="text-sm tracking-widest uppercase text-[#e2e0d8]">Reconstruction Pipeline</h3>
               <p className="text-xs text-[#e2e0d8]/40" style={{ fontFamily: 'var(--font-outfit)' }}>
                 {reconstructionMode === 'ngp' ? 'NVIDIA Instant-NGP (Fast, Real-time)' : 'Classical Mesh (Slower, Geometry focus)'}
               </p>
             </div>
             <div className="flex bg-black p-1 border border-white/10">
               <button 
                 onClick={() => setReconstructionMode('mesh')}
                 className={`px-4 py-2 text-xs tracking-widest uppercase transition-colors ${reconstructionMode === 'mesh' ? 'bg-[#e2e0d8] text-black' : 'text-white/40 hover:text-white'}`}
               >
                 MESH
               </button>
               <button 
                 onClick={() => setReconstructionMode('ngp')}
                 className={`px-4 py-2 text-xs tracking-widest uppercase transition-colors ${reconstructionMode === 'ngp' ? 'bg-[#e2e0d8] text-black' : 'text-white/40 hover:text-white'}`}
               >
                 NGP
               </button>
             </div>
           </div>

           {reconstructionMode === 'ngp' && files.length > 40 && (
             <div className="p-3 bg-yellow-950/30 text-yellow-500/80 text-xs border border-yellow-900/50 uppercase tracking-wider text-center">
               ⚠️ Warning: {files.length} images selected. NGP mode recommends 20-30 images for 4GB VRAM.
             </div>
           )}

           <button 

             onClick={handleUpload} 
             disabled={isUploading || files.length < 10}
             className={`w-full px-6 py-4 font-semibold tracking-[0.2em] uppercase transition-all duration-500 ${isUploading ? 'bg-[#e2e0d8]/20 text-[#e2e0d8] cursor-wait' : files.length >= 10 ? 'bg-[#e2e0d8] text-[#0a0a0a] hover:bg-white' : 'bg-[#111] text-[#e2e0d8]/30 cursor-not-allowed'}`}
             style={{ fontFamily: 'var(--font-outfit)' }}
           >
             {isUploading ? `Initializing Pipeline...` : files.length < 10 ? `Requires ${10 - files.length} more images` : `Run Preprocessing`}
           </button>
         </div>
       </div>
     </div>
  );
}
