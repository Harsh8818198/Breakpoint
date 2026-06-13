'use client';

import { useEffect, useState, useRef } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { Button } from '@/components/ui';
import { 
  Zap, 
  ShieldAlert, 
  Fingerprint, 
  Loader2, 
  Terminal, 
  Activity, 
  AlertCircle, 
  CheckCircle2, 
  User,
  Sparkles,
  ArrowRight,
  TrendingDown,
  Info,
  Layers,
  Search,
  X
} from 'lucide-react';
import { useParams, useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx } from 'clsx';

export default function LiveSimulation() {
  const { id, simId } = useParams();
  const router = useRouter();
  const [status, setStatus] = useState('initializing'); // initializing, generating_agents, running, completed, failed
  const [progress, setProgress] = useState(null);
  const [generation, setGeneration] = useState(0);
  const [findings, setFindings] = useState([]);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState('');
  const logRef = useRef(null);

  useEffect(() => {
    // Establishing SSE Connection
    const eventSource = new EventSource(`/api/simulation/${simId}/stream`);

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'progress') {
        setStatus(data.status);
        setGeneration(data.currentGeneration);
        setProgress(data.progress);
        
        if (data.currentGeneration > 0) {
           addLog(`Generation ${data.currentGeneration} transition initialized.`);
        }
      }

      if (data.type === 'finding') {
        const vuln = data.vulnerability;
        setFindings(prev => [vuln, ...prev]);
        addLog(`ALERT: [Gen ${vuln.generationNumber}] ${vuln.agent} discovered ${vuln.title} (${vuln.severity})`);
      }

      if (data.type === 'complete') {
        setStatus('completed');
        addLog(`Simulation complete. Total findings: ${data.totalFindings}`);
        eventSource.close();
      }

      if (data.type === 'error') {
        setError(data.message);
        setStatus('failed');
        eventSource.close();
      }
    };

    eventSource.onerror = (err) => {
      console.error('SSE Error:', err);
      // Don't close immediately, retry logic is handled by browser
    };

    return () => {
      eventSource.close();
    };
  }, [simId]);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logs]);

  const addLog = (msg) => {
    setLogs(prev => [...prev.slice(-40), { id: Math.random(), msg, time: new Date().toLocaleTimeString() }]);
  };

  const handleGenerateReport = async () => {
    try {
      await fetch(`/api/report/${simId}/generate`, { method: 'POST' });
      router.push(`/projects/${id}/report/${simId}`);
    } catch (error) {
      console.error('Failed to generate report:', error);
    }
  };

  const getStatusText = () => {
    if (status === 'generating_agents') return 'Synthesizing Agent Population...';
    if (status === 'running') return `Evolutionary Discovery Active: Generation ${generation}`;
    if (status === 'completed') return 'Discovery Siege Complete';
    if (status === 'failed') return 'Simulation Engine Failure';
    return 'Initializing Environment...';
  };

  return (
    <AppShell>
      <div className="flex flex-col gap-6 h-[calc(100vh-140px)]">
        {/* Header Container */}
        <div className="flex items-center justify-between pb-4 border-b border-white/5">
          <div className="flex items-center gap-4">
             <div className={clsx(
               'w-12 h-12 rounded-xl flex items-center justify-center transition-all duration-700',
               status === 'running' ? 'bg-[#8b5cf6]/20 text-[#8b5cf6] shadow-[0_0_20px_rgba(139,92,246,0.3)] animate-pulse' : 
               status === 'completed' ? 'bg-[#10b981]/20 text-[#10b981]' : 'bg-white/5 text-[#475569]'
             )}>
                <Zap size={24} />
             </div>
             <div className="flex flex-col">
                <h2 className="text-xl font-bold tracking-tight">{getStatusText()}</h2>
                <div className="flex items-center gap-2">
                   <div className={clsx(
                     'w-2 h-2 rounded-full',
                     status === 'running' ? 'bg-[#8b5cf6] animate-ping' : 
                     status === 'completed' ? 'bg-[#10b981]' : 'bg-[#ef4444]'
                   )} />
                   <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">{status} Mode</span>
                </div>
             </div>
          </div>

          <div className="flex items-center gap-6">
             {status === 'running' && (
               <div className="flex items-center gap-4 px-6 border-x border-white/5">
                  <div className="flex flex-col items-center">
                     <span className="text-2xl font-bold tracking-tighter">{findings.length}</span>
                     <span className="text-[9px] text-[#475569] font-bold uppercase tracking-widest">Findings</span>
                  </div>
                  <div className="h-8 w-px bg-white/10" />
                  <div className="flex flex-col items-center">
                     <span className="text-2xl font-bold tracking-tighter">{progress?.llmCallsMade || 0}</span>
                     <span className="text-[9px] text-[#475569] font-bold uppercase tracking-widest">LLM Invocations</span>
                  </div>
               </div>
             )}

             {status === 'completed' ? (
                <Button onClick={handleGenerateReport} icon={Sparkles} className="animate-glow">
                  Finalize Analytical Report
                </Button>
             ) : (
                <Button variant="secondary" onClick={() => router.push(`/projects/${id}`)}>
                   Monitor in Background
                </Button>
             )}
          </div>
        </div>

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 overflow-hidden flex-grow">
           
           {/* Center Panel: Pulse & Visualizer */}
           <div className="lg:col-span-8 flex flex-col gap-6 overflow-hidden">
              <div className="relative glass-card flex-grow flex flex-col items-center justify-center overflow-hidden border-2 border-[#8b5cf6]/5">
                 {/* Generation Indicator Overlay */}
                 <div className="absolute top-6 left-6 flex items-center gap-5">
                    {[1,2,3,4,5].map(i => (
                      <div key={i} className="flex flex-col items-center gap-2">
                         <div className={clsx(
                           'w-10 h-10 rounded-xl border flex items-center justify-center font-bold text-sm transition-all duration-700',
                           generation === i ? 'bg-[#8b5cf6] border-[#8b5cf6] text-white shadow-[0_0_20px_#8b5cf6]' : 
                           generation > i ? 'bg-[#10b981]/20 border-[#10b981]/20 text-[#10b981]' : 
                           'bg-white/5 border-white/5 text-[#475569]'
                         )}>
                            {generation > i ? <CheckCircle2 size={16} /> : i}
                         </div>
                         <span className={clsx(
                           'text-[8px] font-bold uppercase tracking-widest',
                           generation === i ? 'text-[#8b5cf6]' : 'text-[#475569]'
                         )}>Gen {i}</span>
                      </div>
                    ))}
                 </div>

                 {/* Central Animated Pulse */}
                 <AnimatePresence mode="wait">
                   {status === 'running' && (
                     <motion.div 
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 1.2 }}
                        className="relative"
                     >
                        <div className="w-64 h-64 rounded-full border-2 border-[#8b5cf6]/20 animate-[spin_10s_linear_infinite]" />
                        <div className="absolute inset-4 rounded-full border border-[#06b6d4]/20 animate-[spin_6s_linear_infinite_reverse]" />
                        <div className="absolute inset-0 flex items-center justify-center">
                           <div className="flex flex-col items-center">
                              <Activity size={48} className="text-[#8b5cf6] animate-pulse" />
                              <span className="text-xs font-bold text-[#8b5cf6] uppercase tracking-[0.3em] mt-4 animate-pulse">SIEGING TARGET</span>
                           </div>
                        </div>
                        {/* Orbiting Particles */}
                        {[0, 72, 144, 216, 288].map(deg => (
                          <div 
                            key={deg}
                            className="absolute top-1/2 left-1/2 w-3 h-3 bg-[#8b5cf6] rounded-full shadow-[0_0_15px_#8b5cf6]"
                            style={{ 
                              transform: `rotate(${deg}deg) translate(128px) rotate(-${deg}deg)`,
                              animation: 'pulse 1s infinite alternate'
                            }}
                          />
                        ))}
                     </motion.div>
                   )}
                 </AnimatePresence>

                 {status === 'completed' && (
                   <motion.div 
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="flex flex-col items-center gap-6"
                   >
                      <div className="w-24 h-24 rounded-full bg-[#10b981]/10 flex items-center justify-center text-[#10b981] shadow-[0_0_40px_rgba(16,185,129,0.2)] border border-[#10b981]/20">
                         <CheckCircle2 size={48} />
                      </div>
                      <div className="text-center">
                         <h3 className="text-3xl font-bold tracking-tighter">Evolutionary Cycle Complete</h3>
                         <p className="text-[#64748b] font-medium mt-2">All 5 generations have been modeled and cross-validated.</p>
                      </div>
                      <Button onClick={handleGenerateReport} icon={Sparkles} className="mt-4 animate-bounce">
                        Proceed to Final Intelligence Report
                      </Button>
                   </motion.div>
                 )}

                 {/* Real-time Ticker at Bottom */}
                 <div className="absolute bottom-6 inset-x-6 h-12 bg-black/40 border border-white/5 rounded-2xl flex items-center px-6 gap-6 overflow-hidden">
                    <div className="flex items-center gap-2 shrink-0">
                       <Terminal size={14} className="text-[#8b5cf6]" />
                       <span className="text-[10px] font-bold text-[#64748b] uppercase tracking-widest">Infiltration Ticker:</span>
                    </div>
                    <div className="flex-grow overflow-hidden whitespace-nowrap">
                       <motion.p 
                        key={logs[0]?.id}
                        initial={{ x: 20, opacity: 0 }}
                        animate={{ x: 0, opacity: 1 }}
                        className="text-[10px] font-mono text-[#94a3b8]"
                       >
                        {logs[0]?.msg || 'Establishing secure communication link...'}
                       </motion.p>
                    </div>
                 </div>
              </div>

              {/* Lower Section: Agent Log */}
              <div className="h-64 bg-[#050505] border border-white/5 rounded-2xl overflow-hidden flex flex-col shadow-2xl">
                 <div className="bg-white/5 px-4 py-2 border-b border-white/5 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Terminal size={14} className="text-[#8b5cf6]" />
                      <span className="text-[10px] font-bold text-[#64748b] uppercase tracking-widest">Strategic Infiltration Log</span>
                    </div>
                 </div>
                 <div 
                   ref={logRef}
                   className="flex-grow p-4 font-mono text-[10px] flex flex-col gap-1.5 overflow-y-auto custom-scrollbar"
                 >
                    {logs.map((log) => (
                      <div key={log.id} className="flex items-start gap-4 animate-in fade-in slide-in-from-left-1">
                         <span className="text-[#334155] shrink-0">{log.time}</span>
                         <span className={clsx(
                           'font-medium',
                           log.msg.includes('ALERT') ? 'text-[#ef4444]' : 
                           log.msg.includes('Generation') ? 'text-[#8b5cf6]' : 'text-[#64748b]'
                         )}>{log.msg}</span>
                      </div>
                    ))}
                 </div>
              </div>
           </div>

           {/* Right Panel: Findings Stream */}
           <div className="lg:col-span-4 flex flex-col gap-6 overflow-hidden">
              <div className="flex items-center justify-between">
                 <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest px-2">Discovery Stream</h3>
                 <div className="px-2 py-0.5 rounded-md bg-[#ef4444]/10 text-[#ef4444] text-[8px] font-bold tracking-[0.2em] animate-pulse">LIVE</div>
              </div>

              <div className="flex-grow overflow-y-auto pr-2 flex flex-col gap-3 custom-scrollbar">
                <AnimatePresence initial={false}>
                  {findings.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center gap-4 text-[#334155] border border-dashed border-white/5 rounded-3xl p-10">
                       <Search size={32} className="opacity-20" />
                       <span className="text-[10px] font-bold uppercase tracking-widest text-center">Awaiting initial vulnerability detection...</span>
                    </div>
                  ) : (
                    findings.map((f, i) => (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        className="glass backdrop-blur-xl border-white/5 p-4 rounded-2xl flex flex-col gap-3 group"
                      >
                         <div className="flex items-start justify-between">
                            <div className="flex flex-col gap-1">
                               <div className="flex items-center gap-2">
                                  <span className="text-[9px] font-bold text-[#8b5cf6] bg-[#8b5cf6]/10 px-1.5 py-0.5 rounded uppercase tracking-widest">GEN {f.generationNumber}</span>
                                  <span className="text-[9px] font-bold text-[#475569] uppercase tracking-widest truncate max-w-[120px]">{f.agent}</span>
                               </div>
                               <h4 className="text-sm font-bold tracking-tight mt-1">{f.title}</h4>
                            </div>
                            <div className={clsx(
                              'px-2 py-0.5 rounded-full text-[8px] font-bold uppercase tracking-widest border',
                              f.severity === 'critical' ? 'text-[#ef4444] bg-[#ef4444]/10 border-[#ef4444]/20' : 
                              f.severity === 'high' ? 'text-[#f97316] bg-[#f97316]/10 border-[#f97316]/20' : 
                              'text-[#3b82f6] bg-[#3b82f6]/10 border-[#3b82f6]/20'
                            )}>
                              {f.severity}
                            </div>
                         </div>
                         <div className="flex items-center gap-2">
                            <span className="text-[9px] text-[#475569] font-bold uppercase tracking-widest bg-white/5 px-2 py-0.5 rounded-md">{f.category}</span>
                         </div>
                      </motion.div>
                    ))
                  )}
                </AnimatePresence>
              </div>

              {/* Status Alert */}
              {error && (
                <div className="bg-[#ef4444]/5 border border-[#ef4444]/20 p-4 rounded-2xl flex items-start gap-4">
                   <AlertCircle className="text-[#ef4444] shrink-0" size={20} />
                   <div className="flex flex-col">
                      <span className="text-xs font-bold text-[#ef4444] uppercase tracking-widest">Protocol Breach</span>
                      <p className="text-[10px] font-medium text-[#ef4444]/70 mt-1">{error}</p>
                   </div>
                </div>
              )}
           </div>
        </div>
      </div>
    </AppShell>
  );
}
