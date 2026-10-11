import { createContext, Fragment, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, setApiSessionContext } from "@/api/client";
import type { IdentitySession, WorkspaceSummary } from "@/lib/authSession";

interface WorkspaceContextValue {
  user: IdentitySession["user"];
  workspaces: WorkspaceSummary[];
  activeWorkspace: WorkspaceSummary;
  switching: boolean;
  switchWorkspace: (workspaceId: string) => Promise<void>;
  replaceSession: (session: IdentitySession) => Promise<void>;
  signOut: () => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({ session, onSessionEnded, children }: { session: IdentitySession; onSessionEnded: () => void; children: ReactNode }) {
  const queryClient = useQueryClient();
  const [currentSession, setCurrentSession] = useState(session);
  const [activeWorkspace, setActiveWorkspace] = useState(session.active_workspace);
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    setApiSessionContext({ csrfToken: session.csrf_token, workspaceId: session.active_workspace.id });
    return () => setApiSessionContext(null);
  }, [session]);

  const value = useMemo<WorkspaceContextValue>(() => ({
    user: currentSession.user,
    workspaces: currentSession.workspaces,
    activeWorkspace,
    switching,
    async switchWorkspace(workspaceId) {
      if (workspaceId === activeWorkspace.id || switching) return;
      const next = currentSession.workspaces.find((workspace) => workspace.id === workspaceId);
      if (!next) throw new Error("Workspace is not available to this session");
      setSwitching(true);
      try {
        await queryClient.cancelQueries();
        setApiSessionContext({ csrfToken: currentSession.csrf_token, workspaceId: next.id });
        queryClient.clear();
        setActiveWorkspace(next);
      } finally {
        setSwitching(false);
      }
    },
    async replaceSession(nextSession) {
      await queryClient.cancelQueries();
      setApiSessionContext({ csrfToken: nextSession.csrf_token, workspaceId: nextSession.active_workspace.id });
      queryClient.clear();
      setCurrentSession(nextSession);
      setActiveWorkspace(nextSession.active_workspace);
    },
    async signOut() {
      await api.delete<void>("/auth/session");
      await queryClient.cancelQueries();
      queryClient.clear();
      setApiSessionContext(null);
      onSessionEnded();
    },
  }), [activeWorkspace, currentSession, onSessionEnded, queryClient, switching]);

  return <WorkspaceContext.Provider value={value}><Fragment key={activeWorkspace.id}>{children}</Fragment></WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceContextValue | null {
  return useContext(WorkspaceContext);
}
