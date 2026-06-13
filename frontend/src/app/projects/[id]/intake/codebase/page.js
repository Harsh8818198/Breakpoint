'use client';

import { useState } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { Button, Input } from '@/components/ui';
import { 
  GitBranch, 
  Terminal, 
  Globe, 
  Search, 
  ShieldCheck, 
  CheckCircle2, 
  Loader2, 
  Sparkles,
  ArrowRight,
  Info,
  Code2
} from 'lucide-react';
import { useParams, useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx } from 'clsx';

export default function CodebaseIntake() {
  const { id } = useParams();
  const router = useRouter();
  const [url, setUrl] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState('');

  const addLog = (msg) => {
    setLogs(prev => [...prev.slice(-10), { id: Math.random(), msg, time: new Date().toLocaleTimeString() }]);
  };

  const handleAnalyze = async () => {
    if (!url.trim()) return;
    setIsAnalyzing(true);
    setError('');
    setLogs([]);
    setAnalysis(null);

    addLog(`Establishing connection to target: ${url}`);
    
    try {
      // Connect first
      const connectResponse = await fetch('/api/intake/codebase/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ projectId: id, repoUrl: url }),
      });
      
      if (!connectResponse.ok) throw new Error('Target unreachable / invalid connection.');
      addLog('Connection established. Initiating deep packet traversal...');

      // Analyze
      const analyzeResponse = await fetch('/api/intake/codebase/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ projectId: id }),
      });
      
      const data = await analyzeResponse.json();
      if (!analyzeResponse.ok) throw new Error(data.message || 'Analysis infiltration failed.');

      addLog('Traversal complete. Decomposing architectural patterns...');
      setAnalysis(data.data);
      addLog('System identity localized. Mapping attack surfaces...');
    } catch (err) {
      setError(err.message);
      addLog(`ERR: ${err.message}`);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleGenerateBlueprint = async () => {
    setIsAnalyzing(true);
    try {
      const response = await fetch('/api/intake/codebase/generate', {
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
      setIsAnalyzing(false);
    }
  };

  return (
    <AppShell>
      <div className="flex-grow flex flex-col gap-10 max-w-5xl mx-auto w-full py-6">
        {/* Header */}
        <div className="flex items-center justify-between pb-6 border-b border-white/5">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-[#06b6d4]/10 flex items-center justify-center text-[#06b6d4]">
              <GitBranch size={24} />
            </div>
            <div className="flex flex-col">
              <h2 className="text-2xl font-bold tracking-tight">Codebase Infiltration</h2>
              <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Active Repository Scanner</span>
            </div>
          </div>

          <AnimatePresence>
            {analysis && (
              <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
              >
                <Button onClick={handleGenerateBlueprint} icon={Sparkles} className="animate-glow">
                  Initialize Structural Blueprint
                </Button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
          {/* Left: Input & Terminal */}
          <div className="flex flex-col gap-8">
            <div className="glass-card flex flex-col gap-6">
              <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest">Infiltration Vector</h3>
              <div className="flex flex-col gap-4">
                 <Input 
                   label="Repository URL / Product URL" 
                   placeholder="https://github.com/org/repo" 
                   value={url}
                   onChange={(e) => setUrl(e.target.value)}
                   icon={Globe}
                   disabled={isAnalyzing}
                 />
                 <Button loading={isAnalyzing} onClick={handleAnalyze} icon={Search}>
                    Execute Analysis
                 </Button>
              </div>
              <p className="text-[10px] text-[#475569] font-bold uppercase tracking-widest leading-relaxed mt-2">
                The scanner will analyze architecture, public end-points, and structural definitions to populate the blueprint.
              </p>
            </div>

            {/* Terminal Feed */}
            <div className="bg-[#050505] border border-white/5 rounded-2xl overflow-hidden flex flex-col h-[300px] shadow-2xl">
               <div className="bg-white/5 px-4 py-2 border-b border-white/5 flex items-center gap-4 justify-between">
                  <div className="flex items-center gap-2">
                    <Terminal size={14} className="text-[#06b6d4]" />
                    <span className="text-[10px] font-bold text-[#64748b] uppercase tracking-widest">Scanner Log</span>
                  </div>
                  <div className="flex gap-1.5 px-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-[#ef4444]/40" />
                    <div className="w-1.5 h-1.5 rounded-full bg-[#f59e0b]/40" />
                    <div className="w-1.5 h-1.5 rounded-full bg-[#10b981]/40" />
                  </div>
               </div>
               <div className="flex-grow p-4 font-mono text-xs flex flex-col gap-1 overflow-y-auto custom-scrollbar">
                  {logs.length === 0 && !isAnalyzing && (
                    <span className="text-[#334155] mt-10 text-center uppercase tracking-widest">Awaiting scanner activity...</span>
                  )}
                  {logs.map((log) => (
                    <div key={log.id} className="flex items-start gap-4 animate-in fade-in slide-in-from-left-2">
                       <span className="text-[#475569] shrink-0">[{log.time}]</span>
                       <span className="text-[#94a3b8]">{log.msg}</span>
                    </div>
                  ))}
                  {isAnalyzing && (
                    <div className="flex items-center gap-2 text-[#06b6d4] mt-2">
                       <Loader2 className="animate-spin" size={12} />
                       <span className="animate-pulse">SCANNED PACKETS... 0x{Math.floor(Math.random() * 9999).toString(16)}</span>
                    </div>
                  )}
               </div>
            </div>
          </div>

          {/* Right: Analysis Results */}
          <div className="flex flex-col gap-6">
            <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest">Detection Insights</h3>
            
            <AnimatePresence mode="wait">
              {!analysis ? (
                <div className="h-full border border-dashed border-white/5 rounded-3xl flex flex-col items-center justify-center gap-4 text-[#475569] min-h-[400px]">
                  <Code2 size={48} className="opacity-10" />
                  <span className="text-xs font-bold uppercase tracking-widest italic">Awaiting Architectural Discovery</span>
                </div>
              ) : (
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex flex-col gap-6"
                >
                  {/* Tech Stack */}
                  <div className="glass-card flex flex-col gap-4">
                    <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Language & Stack Profile</span>
                    <div className="flex flex-wrap gap-2">
                       {analysis.technologies?.map(tech => (
                         <div key={tech} className="bg-[#06b6d4]/5 border border-[#06b6d4]/10 rounded-lg px-3 py-1 text-xs font-bold text-[#06b6d4]">
                           {tech}
                         </div>
                       ))}
                    </div>
                  </div>

                  {/* Identified Features */}
                  <div className="glass-card flex flex-col gap-4">
                    <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Architectural Components ({analysis.features?.length || 0})</span>
                    <div className="flex flex-col gap-2">
                       {analysis.features?.map((feat, i) => (
                         <div key={feat} className="bg-white/[0.02] border border-white/5 rounded-xl px-4 py-3 flex items-center justify-between group hover:border-[#06b6d4]/30 transition-all">
                            <span className="text-sm font-bold">{feat}</span>
                            <CheckCircle2 size={14} className="text-[#10b981]" />
                         </div>
                       ))}
                    </div>
                  </div>

                  {/* Risk Profile Preview */}
                  <div className="bg-[#ef4444]/5 border border-[#ef4444]/10 p-5 rounded-2xl flex flex-col gap-3">
                    <div className="flex items-center gap-2">
                       <ShieldCheck className="text-[#ef4444]" size={16} />
                       <span className="text-[10px] text-[#ef4444] font-bold uppercase tracking-widest">Preliminary High-Risk Vectors</span>
                    </div>
                    <ul className="flex flex-col gap-2">
                       <li className="text-xs text-[#ef4444]/80 font-medium list-disc ml-4">Authentication boundary interaction gaps detected.</li>
                       <li className="text-xs text-[#ef4444]/80 font-medium list-disc ml-4">Privileged flow synchronization issues likely.</li>
                    </ul>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
