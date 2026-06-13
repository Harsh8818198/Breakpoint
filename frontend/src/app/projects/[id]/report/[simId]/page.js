'use client';

import { useEffect, useState } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { Button } from '@/components/ui';
import { 
  ShieldAlert, 
  TrendingUp, 
  History, 
  Target, 
  Users, 
  ListTodo, 
  Terminal, 
  ChevronRight,
  Download,
  Share2,
  CheckCircle2,
  AlertCircle,
  Activity,
  Zap,
  Layers,
  Map,
  Fingerprint,
  RotateCcw,
  Clock,
  ArrowRight
} from 'lucide-react';
import { useParams, useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx } from 'clsx';

export default function ReportDashboard() {
  const { id, simId } = useParams();
  const [report, setReport] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [activeSection, setActiveSection] = useState('summary');

  useEffect(() => {
    async function fetchReport() {
      try {
        const response = await fetch(`/api/report/${simId}`);
        const data = await response.json();
        if (data.success) {
          setReport(data.data);
        }
      } catch (error) {
        console.error('Failed to fetch report:', error);
      } finally {
        setIsLoading(false);
      }
    }

    fetchReport();
  }, [simId]);

  if (isLoading) {
    return (
      <AppShell>
        <div className="flex-grow flex flex-col items-center justify-center gap-4">
           <div className="relative">
              <div className="w-16 h-16 border-4 border-[#8b5cf6]/10 rounded-full animate-pulse" />
              <div className="absolute inset-0 flex items-center justify-center">
                 <Zap className="animate-spin text-[#8b5cf6]" size={24} />
              </div>
           </div>
           <p className="text-xs font-bold text-[#475569] uppercase tracking-[0.2em]">Aggregating Analytical Intelligence...</p>
        </div>
      </AppShell>
    );
  }

  const sections = [
    { id: 'summary', label: 'Executive Summary', icon: ShieldAlert },
    { id: 'heatmap', label: 'Attack Heatmap', icon: Target },
    { id: 'clusters', label: 'Threat Clusters', icon: Zap },
    { id: 'vulnerabilities', label: 'Vulnerability Cards', icon: ShieldAlert },
    { id: 'tree', label: 'Evolution Tree', icon: History },
    { id: 'cohorts', label: 'Agent Cohorts', icon: Users },
    { id: 'timeline', label: 'Impact Timeline', icon: TrendingUp },
    { id: 'roadmap', label: 'Remediation', icon: ListTodo },
    { id: 'logs', label: 'Agent Logs', icon: Terminal },
  ];

  return (
    <AppShell>
      <div className="flex flex-col gap-8 max-w-7xl mx-auto w-full py-2">
        {/* Report Header */}
        <div className="flex items-center justify-between pb-6 border-b border-white/5">
          <div className="flex flex-col">
            <h2 className="text-3xl font-bold tracking-tight">Intelligence Discovery Report</h2>
            <div className="flex items-center gap-3 mt-1">
               <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Project: {report?.projectId?.name || 'Infiltrator'}</span>
               <div className="w-1 h-1 bg-white/10 rounded-full" />
               <span className="text-[10px] text-[#8b5cf6] font-bold uppercase tracking-widest">Status: FINALIZED</span>
            </div>
          </div>

          <div className="flex items-center gap-3">
             <Button variant="secondary" icon={Share2}>Share Insight</Button>
             <Button icon={Download}>Export PDF</Button>
          </div>
        </div>

        {/* Sticky Section Navigation */}
        <div className="sticky top-16 z-30 bg-[#050505]/80 backdrop-blur-xl border-b border-white/5 py-3 -mx-8 px-8 flex items-center gap-2 overflow-x-auto no-scrollbar">
           {sections.map(s => (
             <button
              key={s.id}
              onClick={() => {
                setActiveSection(s.id);
                document.getElementById(s.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
              }}
              className={clsx(
                'flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold uppercase tracking-wider transition-all whitespace-nowrap',
                activeSection === s.id ? 'bg-[#8b5cf6] text-white shadow-[0_0_15px_rgba(139,92,246,0.3)]' : 'bg-white/5 text-[#475569] hover:bg-white/10 hover:text-[#94a3b8]'
              )}
             >
                <s.icon size={14} />
                {s.label}
             </button>
           ))}
        </div>

        {/* Global Risk Gauges */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
           {/* Section 1: Executive Summary */}
           <div id="summary" className="lg:col-span-3 glass-card flex flex-col gap-6 scroll-mt-32">
              <div className="flex items-center justify-between">
                 <h3 className="text-lg font-bold">Executive Discovery Summary</h3>
                 <div className={clsx(
                   'px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest border',
                   report.executiveSummary?.overallRiskLevel === 'critical' ? 'text-[#ef4444] border-[#ef4444]/20 bg-[#ef4444]/10' : 'text-[#f59e0b] border-[#f59e0b]/20 bg-[#f59e0b]/10'
                 )}>
                    {report.executiveSummary?.overallRiskLevel} Risk
                 </div>
              </div>
              <p className="text-sm text-[#94a3b8] leading-relaxed font-medium">
                {report.executiveSummary?.summaryText}
              </p>
              <div className="flex items-center gap-4 p-4 rounded-2xl bg-[#ef4444]/5 border border-[#ef4444]/10">
                 <ShieldAlert size={24} className="text-[#ef4444] shrink-0" />
                 <div className="flex flex-col gap-0.5">
                    <span className="text-[9px] text-[#ef4444] font-bold uppercase tracking-widest">Financial Exposure Estimate</span>
                    <span className="text-lg font-bold leading-none">{report.executiveSummary?.estimatedRevenueImpact}</span>
                 </div>
              </div>
           </div>

           {/* Quick Stats Grid */}
           <div className="lg:col-span-2 grid grid-cols-2 gap-4">
              {[
                { label: 'Critical', value: report.executiveSummary?.criticalCount || 0, color: '#ef4444' },
                { label: 'High', value: report.executiveSummary?.highCount || 0, color: '#f97316' },
                { label: 'Medium', value: report.executiveSummary?.mediumCount || 0, color: '#f59e0b' },
                { label: 'Low', value: report.executiveSummary?.lowCount || 0, color: '#3b82f6' },
              ].map(s => (
                <div key={s.label} className="glass-card !p-4 flex flex-col gap-2">
                   <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">{s.label} Severity</span>
                   <div className="flex items-center justify-between">
                      <span className="text-2xl font-bold tracking-tighter" style={{ color: s.color }}>{s.value}</span>
                      <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: s.color, boxShadow: `0 0 8px ${s.color}` }} />
                   </div>
                </div>
              ))}
              <div className="col-span-2 glass-card !p-4 flex items-center justify-between bg-gradient-to-r from-[rgba(139,92,246,0.05)] to-transparent">
                 <div className="flex flex-col gap-0.5">
                    <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Mutation Depth</span>
                    <span className="text-xl font-bold tracking-tight">Level 5 / 5</span>
                 </div>
                 <Layers size={24} className="text-[#8b5cf6] opacity-30" />
              </div>
           </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-12 gap-8">
           {/* Section 2: Attack Heatmap (Left Column) */}
           <div id="heatmap" className="md:col-span-7 flex flex-col gap-6 scroll-mt-32">
              <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest px-2">Attack Surface Criticality Heatmap</h3>
              <div className="glass-card flex flex-col gap-8 h-full">
                 <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {report.attackSurfaceHeatmap?.map((cell, i) => (
                      <div 
                        key={i} 
                        className="p-4 rounded-2xl flex flex-col gap-3 relative overflow-hidden group border border-white/5"
                        style={{ backgroundColor: `rgba(139,92,246, ${cell.intensity / 200})` }}
                      >
                         <div className="flex items-start justify-between">
                            <span className="text-[10px] font-bold uppercase tracking-tighter leading-tight">{cell.feature}</span>
                            <div className={clsx(
                              'w-2 h-2 rounded-full',
                              cell.maxSeverity === 'critical' ? 'bg-[#ef4444]' : 'bg-[#f59e0b]'
                            )} />
                         </div>
                         <div className="flex flex-col">
                            <span className="text-2xl font-bold tracking-tighter">{cell.attackCount}</span>
                            <span className="text-[8px] text-[#475569] font-bold uppercase tracking-widest">Verified Probes</span>
                         </div>
                         {/* Hover Details overlay */}
                         <div className="absolute inset-0 bg-[#8b5cf6] opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center p-2 text-center pointer-events-none">
                            <span className="text-[8px] font-bold uppercase text-white shadow-sm italic">Highest Exposure</span>
                            <span className="font-bold text-xs text-white uppercase">{cell.maxSeverity}</span>
                         </div>
                      </div>
                    ))}
                 </div>
                 <div className="mt-auto bg-white/5 p-4 rounded-xl flex items-center gap-4">
                    <Info size={14} className="text-[#475569]" />
                    <p className="text-[10px] font-medium text-[#475569] uppercase tracking-wider leading-relaxed">
                      Intensity mapping signifies the frequency of successful agent penetrations per feature boundary.
                    </p>
                 </div>
              </div>
           </div>

           {/* Section 3: Threat Clusters (Right Column) */}
           <div id="clusters" className="md:col-span-5 flex flex-col gap-6 scroll-mt-32">
              <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest px-2">Synergistic Threat Narratives</h3>
              <div className="flex flex-col gap-4">
                 {report.threatClusters?.map((cluster, i) => (
                    <motion.div 
                      key={i}
                      initial={{ opacity: 0, x: 20 }}
                      whileInView={{ opacity: 1, x: 0 }}
                      className="glass-card flex flex-col gap-4 border-l-4 border-[#8b5cf6]"
                    >
                       <div className="flex items-center justify-between">
                          <h4 className="text-md font-bold tracking-tight text-[#8b5cf6]">{cluster.theme}</h4>
                          <Zap size={16} className="text-[#8b5cf6]" />
                       </div>
                       <p className="text-xs text-[#94a3b8] font-medium leading-relaxed italic">
                         "{cluster.narrative}"
                       </p>
                       <div className="bg-black/20 border border-white/5 p-3 rounded-xl flex flex-col gap-1">
                          <span className="text-[9px] text-[#475569] font-bold uppercase tracking-widest">Combined Strategic Impact</span>
                          <span className="text-xs font-bold text-[#e2e8f0]">{cluster.combinedImpact}</span>
                       </div>
                    </motion.div>
                 ))}
              </div>
           </div>
        </div>

        {/* Section 4: Vulnerability Cards */}
        <div id="vulnerabilities" className="flex flex-col gap-6 scroll-mt-32">
           <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest px-2">High-Resolution Discovery Cards ({report.vulnerabilityCards?.length || 0})</h3>
           <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {report.vulnerabilityCards?.map((vuln, i) => (
                <motion.div
                  key={vuln._id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                  className="glass-card flex flex-col gap-4 group"
                >
                   <div className="flex items-start justify-between">
                      <div className="flex flex-col gap-1">
                         <div className="flex items-center gap-2">
                            <span className="text-[9px] font-bold text-[#8b5cf6] bg-[#8b5cf6]/10 px-1.5 py-0.5 rounded uppercase tracking-widest">Mutation Gen {vuln.generationNumber}</span>
                            <div 
                              className={clsx(
                                'px-2 py-0.5 rounded-full text-[8px] font-bold uppercase tracking-widest border',
                                vuln.bssScore?.severity === 'critical' ? 'text-[#ef4444] bg-[#ef4444]/10 border-[#ef4444]/20' : 
                                vuln.bssScore?.severity === 'high' ? 'text-[#f97316] bg-[#f97316]/10 border-[#f97316]/20' : 
                                'text-[#3b82f6] bg-[#3b82f6]/10 border-[#3b82f6]/20'
                              )}
                            >
                               {vuln.bssScore?.severity}
                            </div>
                         </div>
                         <h4 className="text-lg font-bold tracking-tight group-hover:text-[#8b5cf6] transition-colors mt-1">{vuln.title}</h4>
                      </div>
                   </div>
                   
                   <p className="text-xs text-[#94a3b8] font-medium leading-relaxed h-[60px] overflow-hidden overflow-ellipsis">
                     {vuln.description}
                   </p>

                   <div className="flex items-center justify-between pt-4 border-t border-white/5">
                      <div className="flex items-center gap-2">
                         <span className="text-[9px] font-bold text-[#475569] uppercase tracking-widest">BSS SCORE</span>
                         <span className="text-sm font-bold text-white">{vuln.bssScore?.totalScore}</span>
                      </div>
                      <div className="flex items-center gap-2">
                         <span className="text-[9px] font-bold text-[#475569] uppercase tracking-widest">EXPL. RATE</span>
                         <span className="text-xs font-bold text-white uppercase">{vuln.impact?.estimatedExploitRate}</span>
                      </div>
                   </div>
                </motion.div>
              ))}
           </div>
        </div>

        {/* Section 5: Evolution Tree */}
        <div id="tree" className="flex flex-col gap-6 scroll-mt-32">
           <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest px-2">Vulnerability Genetic Lineage</h3>
           <div className="glass-card bg-[rgba(139,92,246,0.01)] border-2 border-[#8b5cf6]/5 h-[500px] relative overflow-hidden flex items-center justify-center">
              {/* Tree Visualizer Interface Placeholder */}
              <div className="flex flex-col items-center gap-6">
                 <History size={48} className="text-[#8b5cf6] opacity-20 animate-pulse" />
                 <div className="text-center">
                    <h4 className="text-xl font-bold tracking-tight">Phylogenetic Mutation Map</h4>
                    <p className="text-[#64748b] text-sm mt-1 max-w-sm">The graphical lineage tree shows how Gen 1 base vulnerabilities mutated into Gen 5 emergent systemic threats.</p>
                 </div>
                 <div className="grid grid-cols-2 gap-4">
                    <div className="px-4 py-2 bg-white/5 rounded-xl border border-white/10 flex items-center gap-3">
                       <div className="w-2 h-2 rounded-full bg-[#8b5cf6]" />
                       <span className="text-[10px] font-bold uppercase tracking-widest">Mutation Nodes: {report.evolutionTree?.nodes?.length || 0}</span>
                    </div>
                    <div className="px-4 py-2 bg-white/5 rounded-xl border border-white/10 flex items-center gap-3">
                       <div className="w-2 h-2 rounded-full bg-[#10b981]" />
                       <span className="text-[10px] font-bold uppercase tracking-widest">Evolution Edges: {report.evolutionTree?.edges?.length || 0}</span>
                    </div>
                 </div>
                 {/* Tree Nodes abstraction using circles */}
                 <div className="absolute inset-0 pointer-events-none opacity-[0.2]">
                    {report.evolutionTree?.nodes?.slice(0, 15).map((node, i) => (
                      <div 
                        key={i} 
                        className="absolute w-4 h-4 rounded-full border border-white/20"
                        style={{ 
                          top: `${Math.random() * 80 + 10}%`, 
                          left: `${Math.random() * 80 + 10}%`,
                          borderColor: node.severity === 'critical' ? '#ef4444' : '#8b5cf6'
                        }}
                      />
                    ))}
                 </div>
              </div>
           </div>
        </div>

        {/* Bottom Large Panels: Roadmap & Funnel */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
           {/* Section 8: Remediation Roadmap */}
           <div id="roadmap" className="flex flex-col gap-6 scroll-mt-32">
              <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest px-2">Remediation Strategic Roadmap</h3>
              <div className="flex flex-col gap-3">
                 {[
                   { priorityColor: '#ef4444', label: 'PRE-LAUNCH (P1)', items: report.remediationRoadmap?.priority1 },
                   { priorityColor: '#f59e0b', label: 'NEXT 30 DAYS (P2)', items: report.remediationRoadmap?.priority2 },
                   { priorityColor: '#3b82f6', label: 'MAINTENANCE (P3)', items: report.remediationRoadmap?.priority3 },
                 ].map(group => (
                   <div key={group.label} className="glass-card !p-0 overflow-hidden flex flex-col">
                      <div 
                        className="px-6 py-3 flex items-center justify-between border-b border-white/5"
                        style={{ borderLeft: `4px solid ${group.priorityColor}` }}
                      >
                         <span className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: group.priorityColor }}>{group.label}</span>
                         <span className="text-[10px] text-[#475569] font-bold">{group.items?.length || 0} Actions</span>
                      </div>
                      <div className="flex flex-col divide-y divide-white/[0.03]">
                         {group.items?.map((item, i) => (
                            <div key={i} className="p-4 px-6 flex items-start gap-4 group hover:bg-white/[0.01] transition-colors">
                               <div className="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center shrink-0">
                                  <ArrowRight size={14} className="text-[#475569] group-hover:text-white transition-colors" />
                               </div>
                               <div className="flex flex-col">
                                  <h5 className="font-bold text-sm tracking-tight">{item.title}</h5>
                                  <div className="flex items-center gap-3 mt-1">
                                     <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Effort: {item.effort}</span>
                                     <div className="w-1 h-1 bg-white/10 rounded-full" />
                                     <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest truncate">{item.impact}</span>
                                  </div>
                               </div>
                            </div>
                         ))}
                      </div>
                   </div>
                 ))}
              </div>
           </div>

           {/* Section 7: Impact Timeline */}
           <div id="timeline" className="flex flex-col gap-6 scroll-mt-32">
              <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest px-2">90-Day Simulated Impact Timeline</h3>
              <div className="glass-card flex flex-col gap-10 bg-gradient-to-br from-[#050505] to-[rgba(139,92,246,0.02)]">
                 <div className="relative pl-10 border-l border-white/10 flex flex-col gap-12">
                    {report.simulatedImpactTimeline?.map((t, i) => (
                      <div key={i} className="relative">
                         {/* Bubble indicator */}
                         <div className={clsx(
                           'absolute -left-[45px] w-3 h-3 rounded-full border-4 border-[#050505] shadow-[0_0_10px_rgba(139,92,246,0.5)]',
                           i === 0 ? 'bg-[#ef4444]' : i === 1 ? 'bg-[#f59e0b]' : 'bg-[#8b5cf6]'
                         )} />
                         
                         <div className="flex flex-col gap-2">
                            <span className="text-xs font-bold text-[#8b5cf6] uppercase tracking-widest">{t.period}</span>
                            <h4 className="text-lg font-bold tracking-tight">{t.riskEscalation}</h4>
                            <p className="text-xs text-[#94a3b8] font-medium leading-relaxed italic">
                              {t.description}
                            </p>
                            <div className="flex flex-wrap gap-2 mt-2">
                               {t.keyEvents?.map((ev, k) => (
                                  <div key={k} className="px-3 py-1 bg-white/5 border border-white/5 rounded-lg text-[9px] font-bold uppercase tracking-widest text-[#64748b]">
                                     {ev}
                                  </div>
                               ))}
                            </div>
                         </div>
                      </div>
                    ))}
                 </div>
                 <div className="mt-4 bg-[#ef4444]/5 border border-[#ef4444]/10 p-5 rounded-3xl flex flex-col gap-2">
                    <span className="text-[10px] text-[#ef4444] font-bold uppercase tracking-widest">Critical Terminal Event</span>
                    <p className="text-xs font-medium text-[#ef4444]/80 leading-relaxed uppercase tracking-wider italic">
                      Projected System Failure: Identity integrity loss predicted at ~75 days post-launch if mutation P1 is unaddressed.
                    </p>
                 </div>
              </div>
           </div>
        </div>

        {/* Section 6 & 9: Cohorts & Logs (Small Panels) */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
           {/* Section 6: Agent Cohorts */}
           <div id="cohorts" className="flex flex-col gap-6 scroll-mt-32">
              <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest px-2">Simulated Behavioral Cohorts</h3>
              <div className="grid grid-cols-1 gap-4">
                 {report.agentBehaviorCohorts?.map((c, i) => (
                   <div key={i} className="glass-card flex items-center justify-between group">
                      <div className="flex items-center gap-5">
                         <div className="w-12 h-12 rounded-2xl bg-white/[0.03] border border-white/5 flex flex-col items-center justify-center">
                            <span className="text-lg font-bold tracking-tighter text-[#8b5cf6]">{c.percentage}%</span>
                         </div>
                         <div className="flex flex-col">
                            <span className="font-bold text-sm tracking-tight group-hover:text-[#8b5cf6] transition-colors">{c.cohortName}</span>
                            <span className="text-[9px] text-[#475569] font-bold uppercase tracking-widest mt-0.5">{c.agentCount} Neural Units</span>
                         </div>
                      </div>
                      <div className={clsx(
                        'px-2 py-0.5 rounded-full text-[8px] font-bold uppercase tracking-widest border',
                        c.riskLevel === 'high' || c.riskLevel === 'critical' ? 'text-[#ef4444] border-[#ef4444]/20' : 'text-[#10b981] border-[#10b981]/20'
                      )}>
                         {c.riskLevel}
                      </div>
                   </div>
                 ))}
              </div>
           </div>

           {/* Section 9: Agent Logs Feed */}
           <div id="logs" className="flex flex-col gap-6 scroll-mt-32">
              <h3 className="text-sm font-bold text-[#475569] uppercase tracking-widest px-2">Strategic Reasoning Corpus</h3>
              <div className="glass-card h-[400px] flex flex-col p-6 gap-6 bg-[#050505] border-white/5 shadow-inner">
                 <div className="flex-grow overflow-y-auto pr-2 custom-scrollbar flex flex-col gap-6 font-mono">
                    {report.agentLogs?.slice(0, 10).map((log, i) => (
                      <div key={i} className="flex flex-col gap-2">
                         <div className="flex items-center justify-between border-b border-white/[0.03] pb-1">
                            <span className="text-[10px] text-[#8b5cf6] font-bold uppercase tracking-[0.2em]">{log.persona?.name}</span>
                            <span className="text-[10px] text-[#475569] font-bold">{log.findings?.length || 0} FINDINGS</span>
                         </div>
                         <p className="text-[10px] text-[#64748b] leading-relaxed italic">
                           "{log.fullReasoning?.[0]?.slice(0, 200)}..."
                         </p>
                      </div>
                    ))}
                 </div>
                 <div className="p-3 bg-white/[0.02] border border-white/5 rounded-xl text-center">
                    <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Accessing Full Log Feed: {report.agentLogs?.length || 0} Neural units recorded</span>
                 </div>
              </div>
           </div>
        </div>

        {/* Share Section Bottom */}
        <div className="py-20 flex flex-col items-center gap-10 border-t border-white/5 mt-10">
           <div className="flex flex-col items-center text-center gap-2">
              <CheckCircle2 size={48} className="text-[#10b981]" />
              <h3 className="text-2xl font-bold tracking-tight">Intelligence Discovery Operationalized</h3>
              <p className="text-sm text-[#475569] font-medium max-w-sm">This discovery was executed according to protocol. Intelligence validated and ready for founder-level review.</p>
           </div>
           <div className="flex items-center gap-4">
              <Button variant="secondary" icon={RotateCcw}>Re-discover Mutation</Button>
              <Button icon={Plus} onClick={() => router.push('/projects/new')}>Initialize New Operation</Button>
           </div>
        </div>
      </div>
    </AppShell>
  );
}
