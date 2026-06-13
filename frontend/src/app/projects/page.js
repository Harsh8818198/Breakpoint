'use client';

import { useEffect, useState } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { Button } from '@/components/ui';
import { 
  Plus, 
  Search, 
  Filter, 
  LayoutGrid, 
  List as ListIcon, 
  ArrowUpRight, 
  Clock, 
  ShieldAlert, 
  Fingerprint,
  Zap
} from 'lucide-react';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { formatDistanceToNow } from 'date-fns';
import { clsx } from 'clsx';

export default function Dashboard() {
  const [projects, setProjects] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [viewMode, setViewMode] = useState('grid');
  const [search, setSearch] = useState('');

  useEffect(() => {
    async function fetchProjects() {
      try {
        const response = await fetch('/api/projects');
        const data = await response.json();
        setProjects(data.data || []);
      } catch (error) {
        console.error('Failed to fetch projects:', error);
      } finally {
        setIsLoading(false);
      }
    }

    fetchProjects();
  }, []);

  const stats = [
    { label: 'Total Projects', value: projects.length, icon: LayoutGrid, color: '#94a3b8' },
    { label: 'Active Simulations', value: projects.filter(p => p.status === 'simulating').length, icon: Zap, color: '#8b5cf6' },
    { label: 'Vulnerabilities Identified', value: 124, icon: ShieldAlert, color: '#ef4444' }, // Mock stat for now
    { label: 'Agents Deployed', value: 3420, icon: Fingerprint, color: '#06b6d4' }, // Mock stat for now
  ];

  const filteredProjects = projects.filter(p => 
    p.name?.toLowerCase().includes(search.toLowerCase()) || 
    p.mode?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <AppShell>
      <div className="flex flex-col gap-10">
        {/* Header Section */}
        <div className="flex items-center justify-between">
          <div className="flex flex-col gap-1">
            <h2 className="text-3xl font-bold tracking-tight">Project Dashboard</h2>
            <p className="text-[#64748b] font-medium leading-relaxed">Overview of your ongoing adversarial discoveries.</p>
          </div>
          <Link href="/projects/new">
            <Button icon={Plus}>Analyze New Product</Button>
          </Link>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {stats.map((stat, i) => (
            <motion.div
              key={stat.label}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.1 }}
              className="glass-card flex flex-col gap-4 group"
            >
              <div className="flex items-center justify-between">
                <div className="p-2.5 rounded-xl bg-white/[0.03] border border-white/[0.05] group-hover:border-[#8b5cf6]/30 transition-colors">
                  <stat.icon size={20} style={{ color: stat.color }} />
                </div>
                <div className="flex items-center gap-1 text-[10px] font-bold text-[#10b981] bg-[#10b981]/10 px-2 py-0.5 rounded-full uppercase tracking-widest">
                  <Plus size={10} /> 12%
                </div>
              </div>
              <div className="flex flex-col">
                <span className="text-3xl font-bold tracking-tighter">{stat.value}</span>
                <span className="text-xs text-[#64748b] font-bold uppercase tracking-widest mt-1">{stat.label}</span>
              </div>
            </motion.div>
          ))}
        </div>

        {/* Filters & View Toggle */}
        <div className="flex items-center justify-between gap-4 bg-white/[0.02] border border-white/[0.05] p-2 rounded-2xl">
          <div className="flex-grow relative">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-[#475569]" size={18} />
            <input 
              type="text" 
              placeholder="Filter projects by name or mode..." 
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-transparent border-none py-2.5 pl-12 pr-4 text-sm font-medium focus:ring-0 placeholder:text-[#475569]"
            />
          </div>
          
          <div className="flex items-center gap-2 pr-2">
             <div className="flex bg-black/40 p-1 rounded-xl border border-white/[0.05]">
                <button 
                  onClick={() => setViewMode('grid')}
                  className={clsx('p-1.5 rounded-lg transition-colors', viewMode === 'grid' ? 'bg-white/10 text-white' : 'text-[#475569] hover:text-[#94a3b8]')}
                >
                  <LayoutGrid size={18} />
                </button>
                <button 
                  onClick={() => setViewMode('list')}
                  className={clsx('p-1.5 rounded-lg transition-colors', viewMode === 'list' ? 'bg-white/10 text-white' : 'text-[#475569] hover:text-[#94a3b8]')}
                >
                  <ListIcon size={18} />
                </button>
             </div>
             <Button variant="secondary" className="!px-3 !py-1.5" icon={Filter}>Filter</Button>
          </div>
        </div>

        {/* Projects Grid/List */}
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[1,2,3,4,5,6].map(i => (
              <div key={i} className="glass-card h-[220px] shimmer !bg-none border-dashed border-white/10" />
            ))}
          </div>
        ) : filteredProjects.length === 0 ? (
          <div className="py-20 flex flex-col items-center gap-6 border-2 border-dashed border-white/5 rounded-3xl">
            <div className="w-16 h-16 bg-white/5 rounded-full flex items-center justify-center text-[#475569]">
              <Search size={32} />
            </div>
            <div className="flex flex-col items-center">
              <h3 className="text-xl font-bold">No Discoveries Found</h3>
              <p className="text-sm text-[#475569] mt-1 font-medium">Create a new project to start adversarial testing.</p>
            </div>
            <Link href="/projects/new">
              <Button variant="outline" icon={Plus}>New Project</Button>
            </Link>
          </div>
        ) : (
          <div className={clsx(
            viewMode === 'grid' ? 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6' : 'flex flex-col gap-4'
          )}>
            {filteredProjects.map((project, i) => (
              <ProjectCard key={project._id} project={project} index={i} viewMode={viewMode} />
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}

function ProjectCard({ project, index, viewMode }) {
  const statusColors = {
    ready: '#10b981',
    interrogating: '#8b5cf6',
    simulating: '#f59e0b',
    completed: '#3b82f6',
    failed: '#ef4444',
  };

  const modeIcons = {
    conversation: '💬',
    document: '📄',
    codebase: '📁',
  };

  if (viewMode === 'list') {
    return (
      <motion.div
        initial={{ opacity: 0, x: -10 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: index * 0.05 }}
        className="glass-card !p-4 flex items-center justify-between group"
      >
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-white/[0.03] border border-white/[0.05] flex items-center justify-center text-xl">
            {modeIcons[project.mode] || '📦'}
          </div>
          <div className="flex flex-col">
            <h3 className="font-bold tracking-tight group-hover:text-[#8b5cf6] transition-colors">{project.name}</h3>
            <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">{project.mode} intake</span>
          </div>
        </div>

        <div className="flex items-center gap-12">
           <div className="flex flex-col items-end">
              <div className="flex items-center gap-2">
                <div 
                  className="w-2 h-2 rounded-full" 
                  style={{ backgroundColor: statusColors[project.status] || '#94a3b8', boxShadow: `0 0 10px ${statusColors[project.status] || '#94a3b8'}` }} 
                />
                <span className="text-xs font-bold uppercase tracking-widest" style={{ color: statusColors[project.status] || '#94a3b8' }}>
                  {project.status}
                </span>
              </div>
              <span className="text-[10px] text-[#475569] font-medium mt-0.5 uppercase tracking-widest">Global Status</span>
           </div>

           <div className="flex flex-col items-end">
              <span className="text-xs font-bold">{formatDistanceToNow(new Date(project.updatedAt), { addSuffix: true })}</span>
              <span className="text-[10px] text-[#475569] font-medium uppercase tracking-widest mt-0.5">Last Modification</span>
           </div>

           <Link href={`/projects/${project._id}`}>
              <Button variant="ghost" className="!p-2">
                <ArrowUpRight size={20} className="group-hover:rotate-45 transition-transform" />
              </Button>
           </Link>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1 }}
      className="glass-card flex flex-col gap-6 group"
    >
      <div className="flex items-start justify-between">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-white/[0.03] border border-white/[0.05] flex items-center justify-center text-sm">
              {modeIcons[project.mode] || '📦'}
            </div>
            <h3 className="text-lg font-bold tracking-tight group-hover:text-[#8b5cf6] transition-colors">{project.name}</h3>
          </div>
          <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest pl-11">{project.mode} intake mode active</span>
        </div>
        <div 
          className="px-2.5 py-0.5 rounded-full text-[10px] font-bold border border-white/[0.05] uppercase tracking-[0.2em]"
          style={{ 
            color: statusColors[project.status] || '#94a3b8', 
            backgroundColor: `${statusColors[project.status]}10` || 'transparent',
            borderColor: `${statusColors[project.status]}30` || 'transparent'
          }}
        >
          {project.status}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="bg-white/[0.02] border border-white/[0.05] p-3 rounded-2xl flex flex-col gap-1">
          <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Findings</span>
          <div className="flex items-center gap-2">
             <ShieldAlert size={14} className="text-[#ef4444]" />
             <span className="text-sm font-bold">12 Active</span>
          </div>
        </div>
        <div className="bg-white/[0.02] border border-white/[0.05] p-3 rounded-2xl flex flex-col gap-1">
          <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">Generation</span>
          <div className="flex items-center gap-2">
             <Clock size={14} className="text-[#3b82f6]" />
             <span className="text-sm font-bold">Gen 4/5</span>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between pt-2 border-t border-white/[0.05]">
        <span className="text-[10px] text-[#475569] font-bold uppercase tracking-widest">
          Modified {formatDistanceToNow(new Date(project.updatedAt), { addSuffix: true })}
        </span>
        <Link href={`/projects/${project._id}`}>
          <Button variant="secondary" className="!px-4 !py-1.5 !text-xs group-hover:bg-[#8b5cf6] group-hover:text-white transition-all">
            Access Controls
          </Button>
        </Link>
      </div>
    </motion.div>
  );
}
