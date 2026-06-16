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
  Info,
  Code2,
  FolderOpen,
  Key,
  ArrowRight
} from 'lucide-react';
import { useParams, useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx } from 'clsx';

const TABS = [
  { id: 'github', label: 'GitHub Repository', icon: GitBranch, color: '#8b5cf6' },
  { id: 'local', label: 'Local Path', icon: FolderOpen, color: '#06b6d4' },
];

export default function CodebaseIntake() {
  const { id } = useParams();
  const router = useRouter();
  const [activeTab, setActiveTab] = useState('github');

  // GitHub flow state
  const [url, setUrl] = useState('');
  const [accessToken, setAccessToken] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState('');

  // Local path flow state
  const [localPath, setLocalPath] = useState('');
  const [isLocalScanning, setIsLocalScanning] = useState(false);
  const [localResult, setLocalResult] = useState(null);
  const [localError, setLocalError] = useState('');

  const addLog = (msg) => {
    setLogs(prev => [...prev.slice(-10), { id: Math.random(), msg, time: new Date().toLocaleTimeString() }]);
  };

  // ─── GitHub Flow ───
  const handleAnalyze = async () => {
    if (!url.trim()) return;
    setIsAnalyzing(true);
    setError('');
    setLogs([]);
    setAnalysis(null);

    addLog(`Establishing connection to target: ${url}`);
    
    try {
      const connectResponse = await fetch('/api/intake/codebase/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ projectId: id, repoUrl: url, accessToken }),
      });
      
      if (!connectResponse.ok) throw new Error('Target unreachable / invalid connection.');
      addLog('Connection established. Initiating deep packet traversal...');

      const analyzeResponse = await fetch('/api/intake/codebase/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ projectId: id, accessToken }),
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

  const handleGenerateBlueprintGitHub = async () => {
    setIsAnalyzing(true);
    try {
      const response = await fetch('/api/intake/codebase/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ projectId: id, accessToken }),
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

  // ─── Local Path Flow ───
  const handleLocalScan = async () => {
    if (!localPath.trim()) return;
    setIsLocalScanning(true);
    setLocalError('');
    setLocalResult(null);

    try {
      const response = await fetch('/api/intake/codebase/local', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ projectId: id, localPath: localPath.trim() }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || 'Scan failed');
      setLocalResult(data.data);
    } catch (err) {
      setLocalError(err.message);
    } finally {
      setIsLocalScanning(false);
    }
  };

  const handleGenerateBlueprintLocal = async () => {
    router.push(`/projects/${id}/blueprint`);
  };

  return (
    <AppShell>
      <div className="flex-grow flex flex-col gap-10 max-w-5xl mx-auto w-full py-6">
        {/* Header */}
        <div className="flex items-center justify-between pb-6 border-b border-white/5">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-[#06b6d4]/10 flex items-center justify-center text-[#06b6d4]">
              <Code2 size={24} />
            </div>
            <div className="flex flex-col">
              <h2 className="text-2xl font-bold tracking-tight">Codebase Infiltration</h2>
              <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Active Repository Scanner</span>
            </div>
          </div>

          {(analysis || localResult) && (
            <div>
              <Button 
                onClick={activeTab === 'github' ? handleGenerateBlueprintGitHub : handleGenerateBlueprintLocal} 
                icon={Sparkles} 
                className="animate-glow"
                loading={isAnalyzing || isLocalScanning}
              >
                Initialize Structural Blueprint
              </Button>
            </div>
          )}
        </div>

        {/* Tab Switcher */}
        <div className="flex gap-1 p-1 bg-white/[0.03] border border-white/5 rounded-2xl w-fit">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={clsx(
                'flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold uppercase tracking-widest transition-all',
                activeTab === tab.id
                  ? 'bg-white/[0.06] text-white shadow-sm'
                  : 'text-[#475569] hover:text-white'
              )}
            >
              <tab.icon size={14} style={{ color: activeTab === tab.id ? tab.color : undefined }} />
              {tab.label}
            </button>
          ))}
        </div>

        <AnimatePresence mode="wait">
          {activeTab === 'github' ? (
            <motion.div
              key="github"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="grid grid-cols-1 md:grid-cols-2 gap-10"
            >
              {/* Left: Input & Terminal */}
              <div className="flex flex-col gap-8">
                <div className="glass-card flex flex-col gap-6">
                  <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest">GitHub Infiltration Vector</h3>
                  <div className="flex flex-col gap-4">
                    <Input 
                      label="Repository URL" 
                      placeholder="https://github.com/org/repo" 
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      icon={Globe}
                      disabled={isAnalyzing}
                    />
                    <Input 
                      label="GitHub Access Token" 
                      placeholder="ghp_xxxxxxxxxxxxxxxxxxxx" 
                      value={accessToken}
                      onChange={(e) => setAccessToken(e.target.value)}
                      icon={Key}
                      disabled={isAnalyzing}
                      type="password"
                    />
                    <Button loading={isAnalyzing} onClick={handleAnalyze} icon={Search}>
                       Execute Analysis
                    </Button>
                  </div>
                  <p className="text-[10px] text-[#475569] font-bold uppercase tracking-widest leading-relaxed mt-2">
                    Requires read access to the repository. A fine-grained token with <code className="text-[#06b6d4]">contents: read</code> scope is sufficient.
                  </p>
                </div>

                {/* Terminal Feed */}
                <div className="bg-[#050505] border border-white/5 rounded-2xl overflow-hidden flex flex-col h-[300px] shadow-2xl">
                   <div className="bg-white/5 px-4 py-2 border-b border-white/5 flex items-center gap-4 justify-between">
                      <div className="flex items-center gap-2">
                        <Terminal size={14} className="text-[#8b5cf6]" />
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
                           <span className={clsx('', log.msg.startsWith('ERR') ? 'text-[#ef4444]' : 'text-[#94a3b8]')}>{log.msg}</span>
                        </div>
                      ))}
                      {isAnalyzing && (
                        <div className="flex items-center gap-2 text-[#8b5cf6] mt-2">
                           <Loader2 className="animate-spin" size={12} />
                           <span className="animate-pulse">TRAVERSING COMMIT GRAPH...</span>
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
                      <div className="glass-card flex flex-col gap-4">
                        <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Tech Stack Profile</span>
                        <div className="flex flex-wrap gap-2">
                           {analysis.technologies?.map(tech => (
                             <div key={tech} className="bg-[#06b6d4]/5 border border-[#06b6d4]/10 rounded-lg px-3 py-1 text-xs font-bold text-[#06b6d4]">
                               {tech}
                             </div>
                           ))}
                        </div>
                      </div>
                      <div className="glass-card flex flex-col gap-4">
                        <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Architectural Components ({analysis.features?.length || 0})</span>
                        <div className="flex flex-col gap-2">
                           {analysis.features?.map((feat) => (
                             <div key={feat} className="bg-white/[0.02] border border-white/5 rounded-xl px-4 py-3 flex items-center justify-between">
                                <span className="text-sm font-bold">{feat}</span>
                                <CheckCircle2 size={14} className="text-[#10b981]" />
                             </div>
                           ))}
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="local"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="grid grid-cols-1 md:grid-cols-2 gap-10"
            >
              {/* Left: Local Path Input */}
              <div className="flex flex-col gap-8">
                <div className="glass-card flex flex-col gap-6">
                  <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest">Local Directory Scanner</h3>
                  <div className="flex flex-col gap-4">
                    <div className="flex flex-col gap-2">
                      <label className="text-xs font-bold text-[#475569] uppercase tracking-widest">Directory Path</label>
                      <div className="flex items-center gap-2 bg-[rgba(255,255,255,0.03)] border border-white/5 rounded-xl px-4 py-2.5 focus-within:ring-1 focus-within:ring-[#06b6d4] focus-within:border-[#06b6d4]">
                        <FolderOpen size={16} className="text-[#06b6d4] shrink-0" />
                        <input
                          type="text"
                          placeholder="C:\Projects\my-app  or  /home/user/project"
                          value={localPath}
                          onChange={(e) => setLocalPath(e.target.value)}
                          disabled={isLocalScanning}
                          className="w-full bg-transparent border-none text-sm font-medium focus:ring-0 placeholder:text-[#334155] outline-none font-mono"
                        />
                      </div>
                    </div>
                    <Button loading={isLocalScanning} onClick={handleLocalScan} icon={Search}>
                       Execute Local Scan
                    </Button>
                  </div>
                  
                  {localError && (
                    <div className="bg-[#ef4444]/5 border border-[#ef4444]/20 p-3 rounded-xl">
                      <p className="text-xs text-[#ef4444] font-medium">{localError}</p>
                    </div>
                  )}

                  <div className="bg-[#06b6d4]/5 border border-[#06b6d4]/10 p-4 rounded-2xl flex items-start gap-3">
                     <Info size={16} className="text-[#06b6d4] shrink-0 mt-0.5" />
                     <p className="text-[10px] font-bold text-[#94a3b8] uppercase tracking-wider leading-relaxed">
                       The Python backend must be running locally. The scanner will recursively analyze your codebase and auto-prioritize routes, models, auth, and payment files.
                     </p>
                  </div>
                </div>
              </div>

              {/* Right: Scan Results */}
              <div className="flex flex-col gap-6">
                <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest">Scan Results</h3>

                <AnimatePresence mode="wait">
                  {!localResult ? (
                    <div className="h-full border border-dashed border-white/5 rounded-3xl flex flex-col items-center justify-center gap-4 text-[#475569] min-h-[400px]">
                      {isLocalScanning ? (
                        <div className="flex flex-col items-center gap-4">
                          <Loader2 size={40} className="text-[#06b6d4] animate-spin" />
                          <span className="text-xs font-bold uppercase tracking-widest text-[#06b6d4] animate-pulse">Scanning Codebase...</span>
                        </div>
                      ) : (
                        <>
                          <FolderOpen size={48} className="opacity-10" />
                          <span className="text-xs font-bold uppercase tracking-widest italic">Enter a local directory path to scan</span>
                        </>
                      )}
                    </div>
                  ) : (
                    <motion.div
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="flex flex-col gap-6"
                    >
                      <div className="glass-card flex flex-col gap-4">
                        <div className="flex items-center gap-2">
                          <CheckCircle2 size={16} className="text-[#10b981]" />
                          <span className="text-sm font-bold text-[#10b981]">Scan Complete</span>
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                          <div className="bg-white/[0.02] border border-white/5 rounded-xl p-4 flex flex-col gap-1">
                            <span className="text-2xl font-bold tracking-tighter">{localResult.filesScanned || 0}</span>
                            <span className="text-[9px] text-[#475569] font-bold uppercase tracking-widest">Files Scanned</span>
                          </div>
                          <div className="bg-white/[0.02] border border-white/5 rounded-xl p-4 flex flex-col gap-1">
                            <span className="text-2xl font-bold tracking-tighter">{localResult.entitiesFound || 0}</span>
                            <span className="text-[9px] text-[#475569] font-bold uppercase tracking-widest">Entities Found</span>
                          </div>
                        </div>
                        {localResult.categories && (
                          <div className="flex flex-wrap gap-2 mt-2">
                            {Object.entries(localResult.categories).map(([cat, count]) => count > 0 && (
                              <div key={cat} className="bg-[#06b6d4]/5 border border-[#06b6d4]/10 rounded-lg px-3 py-1 text-xs font-bold text-[#06b6d4]">
                                {cat}: {count}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>

                      <div className="bg-[#10b981]/5 border border-[#10b981]/10 p-5 rounded-2xl flex flex-col gap-3">
                        <div className="flex items-center gap-2">
                           <ShieldCheck className="text-[#10b981]" size={16} />
                           <span className="text-[10px] text-[#10b981] font-bold uppercase tracking-widest">Blueprint Ready</span>
                        </div>
                        <p className="text-xs text-[#64748b] font-medium leading-relaxed">
                          The Python engine has compiled your codebase into a blueprint. Click "Initialize Structural Blueprint" to persist it and proceed.
                        </p>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </AppShell>
  );
}
