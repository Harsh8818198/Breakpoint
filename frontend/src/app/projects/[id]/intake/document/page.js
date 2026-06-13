'use client';

import { useState, useRef } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { Button } from '@/components/ui';
import { 
  FileText, 
  Upload, 
  X, 
  FileCheck, 
  Loader2, 
  Sparkles,
  Search,
  CheckCircle2,
  Trash2,
  Info
} from 'lucide-react';
import { useParams, useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx } from 'clsx';

export default function DocumentIntake() {
  const { id } = useParams();
  const router = useRouter();
  const [files, setFiles] = useState([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const fileInputRef = useRef(null);

  const handleFileChange = (e) => {
    const selectedFiles = Array.from(e.target.files);
    addFiles(selectedFiles);
  };

  const addFiles = (selectedFiles) => {
    const newFiles = selectedFiles.map(f => ({
      id: Math.random().toString(36).substr(2, 9),
      file: f,
      name: f.name,
      size: (f.size / 1024 / 1024).toFixed(2) + ' MB',
      status: 'pending', // pending, parsing, parsed, error
      progress: 0,
      content: null
    }));
    setFiles(prev => [...prev, ...newFiles]);
  };

  const removeFile = (id) => {
    setFiles(prev => prev.filter(f => f.id !== id));
  };

  const uploadAndParse = async () => {
    setIsUploading(true);
    
    // We upload each file via /api/intake/document/upload
    // Note: The backend expects a 'file' parameter (form-data)
    for (const fileObj of files) {
      if (fileObj.status === 'parsed') continue;

      setFiles(prev => prev.map(f => f.id === fileObj.id ? { ...f, status: 'parsing' } : f));

      try {
        const formData = new FormData();
        formData.append('file', fileObj.file);
        formData.append('projectId', id);

        const response = await fetch('/api/intake/document/upload', {
          method: 'POST',
          body: formData,
        });
        
        const data = await response.json();
        
        if (data.success) {
          setFiles(prev => prev.map(f => f.id === fileObj.id ? { ...f, status: 'parsed', content: data.data } : f));
        } else {
          setFiles(prev => prev.map(f => f.id === fileObj.id ? { ...f, status: 'error', error: data.message } : f));
        }
      } catch (error) {
        setFiles(prev => prev.map(f => f.id === fileObj.id ? { ...f, status: 'error', error: 'Network error' } : f));
      }
    }
    
    setIsUploading(false);
  };

  const handleGenerateBlueprint = async () => {
    setIsGenerating(true);
    try {
      const response = await fetch('/api/intake/document/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ projectId: id }),
      });
      const data = await response.json();
      if (data.success) {
        router.push(`/projects/${id}/blueprint`);
      }
    } catch (error) {
      console.error('Failed to generate blueprint:', error);
      setIsGenerating(false);
    }
  };

  const allParsed = files.length > 0 && files.every(f => f.status === 'parsed');

  return (
    <AppShell>
      <div className="flex-grow flex flex-col gap-10 max-w-5xl mx-auto w-full py-6">
        {/* Header */}
        <div className="flex items-center justify-between pb-6 border-b border-white/5">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-[#3b82f6]/10 flex items-center justify-center text-[#3b82f6]">
              <FileText size={24} />
            </div>
            <div className="flex flex-col">
              <h2 className="text-2xl font-bold tracking-tight">Vault Secure Parser</h2>
              <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Document Infiltration Vector</span>
            </div>
          </div>

          <AnimatePresence>
            {allParsed && (
              <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
              >
                <Button loading={isGenerating} onClick={handleGenerateBlueprint} icon={Sparkles} className="animate-glow">
                  Initialize Structural Blueprint
                </Button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-10">
          {/* Left: Upload Zone */}
          <div className="md:col-span-1 flex flex-col gap-6">
            <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest">Ingestion Zone</h3>
            
            <div 
              onClick={() => fileInputRef.current?.click()}
              className={clsx(
                'group flex-grow h-[300px] border-2 border-dashed rounded-3xl transition-all duration-500 cursor-pointer flex flex-col items-center justify-center gap-4',
                files.length === 0 ? 'bg-white/[0.02] border-white/10 hover:border-[#3b82f6]/40 hover:bg-[#3b82f6]/5' : 'bg-[#10b981]/5 border-[#10b981]/10'
              )}
            >
              <input 
                type="file" 
                ref={fileInputRef} 
                onChange={handleFileChange} 
                multiple 
                hidden 
                accept=".pdf,.docx,.doc,.yaml,.json,.txt"
              />
              
              <div className={clsx(
                'w-16 h-16 rounded-2xl flex items-center justify-center transition-all duration-500',
                files.length === 0 ? 'bg-white/5 text-[#475569] group-hover:text-[#3b82f6] group-hover:scale-110' : 'bg-[#10b981]/10 text-[#10b981]'
              )}>
                 {files.length === 0 ? <Upload size={32} /> : <FileCheck size={32} />}
              </div>

              <div className="flex flex-col items-center text-center px-6">
                <span className="font-bold text-sm tracking-tight">
                  {files.length === 0 ? 'Inject Documentation' : `${files.length} Vectors Registered`}
                </span>
                <p className="text-[10px] text-[#475569] font-bold uppercase tracking-widest mt-1">
                  PDF, DOCX, YAML, JSON admitted
                </p>
              </div>

              {files.length > 0 && files.some(f => f.status === 'pending') && (
                <Button 
                  loading={isUploading}
                  onClick={(e) => { e.stopPropagation(); uploadAndParse(); }}
                  className="mt-4 !py-2 !text-xs !px-4"
                  icon={Search}
                >
                  Start Analysis
                </Button>
              )}
            </div>

            <div className="bg-[#3b82f6]/5 border border-[#3b82f6]/10 p-4 rounded-2xl flex items-start gap-4">
               <div className="p-2 bg-[#3b82f6]/10 rounded-lg text-[#3b82f6]">
                  <Info size={16} />
               </div>
               <p className="text-[10px] font-bold text-[#94a3b8] uppercase tracking-wider leading-relaxed">
                 The parser will decompose these documents using switchable intelligence layers to identify project entities.
               </p>
            </div>
          </div>

          {/* Right: File List */}
          <div className="md:col-span-2 flex flex-col gap-6">
            <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest">Target Inventory</h3>

            {files.length === 0 ? (
              <div className="h-full border border-dashed border-white/5 rounded-3xl flex flex-col items-center justify-center gap-4 text-[#475569]">
                <FileText size={48} className="opacity-20" />
                <span className="text-xs font-bold uppercase tracking-widest">Awaiting File Infiltration</span>
              </div>
            ) : (
              <div className="flex flex-col gap-4 overflow-y-auto max-h-[600px] pr-2 custom-scrollbar">
                <AnimatePresence initial={false}>
                  {files.map((f, i) => (
                    <motion.div
                      key={f.id}
                      initial={{ opacity: 0, x: 20 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, scale: 0.95 }}
                      className="glass backdrop-blur-xl border-white/5 p-4 rounded-2xl flex items-center justify-between group"
                    >
                      <div className="flex items-center gap-4">
                        <div className={clsx(
                          'w-12 h-12 rounded-xl flex items-center justify-center transition-colors',
                          f.status === 'parsed' ? 'bg-[#10b981]/10 text-[#10b981]' : 
                          f.status === 'parsing' ? 'bg-[#3b82f6]/10 text-[#3b82f6]' : 
                          'bg-white/5 text-[#475569]'
                        )}>
                          {f.status === 'parsing' ? <Loader2 className="animate-spin" size={24} /> : <FileText size={24} />}
                        </div>
                        <div className="flex flex-col">
                           <span className="font-bold text-sm tracking-tight">{f.name}</span>
                           <div className="flex items-center gap-2 mt-0.5">
                              <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">{f.size}</span>
                              <div className="w-1 h-1 bg-white/10 rounded-full" />
                              <span className={clsx(
                                'text-[10px] font-bold uppercase tracking-widest',
                                f.status === 'parsed' ? 'text-[#10b981]' : 
                                f.status === 'parsing' ? 'text-[#3b82f6]' : 
                                f.status === 'error' ? 'text-[#ef4444]' : 'text-[#475569]'
                              )}>
                                {f.status} {f.status === 'error' ? `- ${f.error}` : ''}
                              </span>
                           </div>
                        </div>
                      </div>

                      <button 
                        onClick={() => removeFile(f.id)}
                        className="p-2 text-[#475569] hover:text-[#ef4444] transition-colors"
                      >
                        <Trash2 size={16} />
                      </button>
                    </motion.div>
                  ))}
                </AnimatePresence>
              </div>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
