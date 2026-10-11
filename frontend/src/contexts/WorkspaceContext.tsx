import { createContext, Fragment, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { setApiSessionContext } from "@/api/client";
import type { IdentitySession, WorkspaceSummary } from "@/lib/authSession";

interface WorkspaceContextValue {
  user: IdentitySession["user"];
  workspaces: WorkspaceSummary[];
  activeWorkspace: WorkspaceSummary;
  switching: boolean;
  switchWorkspace: (workspaceId: string) => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({ session, children }: { session: IdentitySession; children: ReactNode }) {
  const queryClient = useQueryClient();
  const [activeWorkspace, setActiveWorkspace] = useState(session.active_workspace);
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    setApiSessionContext({ csrfToken: session.csrf_token, workspaceId: session.active_workspace.id });
    return () => setApiSessionContext(null);
  }, [session]);

  const value = useMemo<WorkspaceContextValue>(() => ({
    user: session.user,
    workspaces: session.workspaces,
    activeWorkspace,
    switching,
    async switchWorkspace(workspaceId) {
      if (workspaceId === activeWorkspace.id || switching) return;
      const next = session.workspaces.find((workspace) => workspace.id === workspaceId);
      if (!next) throw new Error("Workspace is not available to this session");
      setSwitching(true);
      try {
        await queryClient.cancelQueries();
        setApiSessionContext({ csrfToken: session.csrf_token, workspaceId: next.id });
        queryClient.clear();
        setActiveWorkspace(next);
      } finally {
        setSwitching(false);
      }
    },
  }), [activeWorkspace, queryClient, session, switching]);

  return <WorkspaceContext.Provider value={value}><Fragment key={activeWorkspace.id}>{children}</Fragment></WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceContextValue | null {
  return useContext(WorkspaceContext);
}
