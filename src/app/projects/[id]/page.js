'use client';

import { useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { AppShell } from '@/components/layout/AppShell';
import { Loader2 } from 'lucide-react';

export default function ProjectRedirect() {
  const { id } = useParams();
  const router = useRouter();

  useEffect(() => {
    async function redirectWorkflow() {
      try {
        const response = await fetch(`/api/projects/${id}`);
        const data = await response.json();
        if (data.success) {
          const project = data.data;
          const status = project.status;
          const intakeMode = project.intakeMode || 'conversation';

          if (status === 'intake') {
            router.replace(`/projects/${id}/intake/${intakeMode}`);
          } else if (status === 'verification') {
            router.replace(`/projects/${id}/blueprint`);
          } else if (status === 'ready') {
            router.replace(`/projects/${id}/simulate/configure`);
          } else if (status === 'simulating') {
            const simId = project.simulationIds?.[project.simulationIds.length - 1];
            if (simId) {
              router.replace(`/projects/${id}/simulate/${simId}`);
            } else {
              router.replace(`/projects/${id}/simulate/configure`);
            }
          } else if (status === 'completed') {
            const simId = project.simulationIds?.[project.simulationIds.length - 1];
            if (simId) {
              router.replace(`/projects/${id}/report/${simId}`);
            } else {
              router.replace(`/projects/${id}/simulate/configure`);
            }
          } else {
            router.replace(`/projects/${id}/intake/${intakeMode}`);
          }
        } else {
          router.replace('/projects');
        }
      } catch (error) {
        console.error('Failed to route project:', error);
        router.replace('/projects');
      }
    }

    redirectWorkflow();
  }, [id, router]);

  return (
    <AppShell>
      <div className="flex-grow flex flex-col items-center justify-center gap-4">
        <Loader2 className="animate-spin text-[#8b5cf6]" size={40} />
        <p className="text-sm font-bold text-[#475569] uppercase tracking-widest">Routing to active workspace...</p>
      </div>
    </AppShell>
  );
}
