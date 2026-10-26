import { createContext, Fragment, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, setApiSessionContext, WORKSPACE_BLOCKED_EVENT } from "@/api/client";
import type { IdentitySession, WorkspaceStatus, WorkspaceSummary } from "@/lib/authSession";

interface WorkspaceContextValue {
  user: IdentitySession["user"];
  workspaces: WorkspaceSummary[];
  activeWorkspace: WorkspaceSummary;
  switching: boolean;
  switchWorkspace: (workspaceId: string) => Promise<void>;
  replaceSession: (session: IdentitySession) => Promise<void>;
  /** Reflects an admin block/unblock without another server round trip. */
  setWorkspaceStatus: (workspaceId: string, status: WorkspaceStatus) => void;
  /** Forgets a deleted workspace and, if it was active, opens an open one. */
  dropWorkspace: (workspaceId: string) => Promise<void>;
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

  // A workspace can be blocked while it is open; finance calls then answer 423.
  useEffect(() => {
    const onBlocked = (event: Event) => {
      const workspaceId = (event as CustomEvent<string>).detail;
      setCurrentSession((current) => withStatus(current, workspaceId, "blocked"));
      setActiveWorkspace((current) => (current.id === workspaceId ? { ...current, status: "blocked" } : current));
    };
    window.addEventListener(WORKSPACE_BLOCKED_EVENT, onBlocked);
    return () => window.removeEventListener(WORKSPACE_BLOCKED_EVENT, onBlocked);
  }, []);

  const value = useMemo<WorkspaceContextValue>(() => ({
    user: currentSession.user,
    workspaces: currentSession.workspaces,
    activeWorkspace,
    switching,
    async switchWorkspace(workspaceId) {
      if (workspaceId === activeWorkspace.id || switching) return;
      const next = currentSession.workspaces.find((workspace) => workspace.id === workspaceId);
      if (!next) throw new Error("Workspace is not available to this session");
      if (next.status === "blocked") throw new Error("Workspace is blocked");
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
    setWorkspaceStatus(workspaceId, status) {
      setCurrentSession((current) => withStatus(current, workspaceId, status));
      setActiveWorkspace((current) => (current.id === workspaceId ? { ...current, status } : current));
    },
    async dropWorkspace(workspaceId) {
      const remaining = currentSession.workspaces.filter((workspace) => workspace.id !== workspaceId);
      if (remaining.length === currentSession.workspaces.length) return;
      if (remaining.length === 0) {
        onSessionEnded();
        return;
      }
      const next = activeWorkspace.id === workspaceId
        ? remaining.find((workspace) => workspace.kind === "personal" && workspace.status === "active")
          ?? remaining.find((workspace) => workspace.status === "active")
          ?? remaining[0]
        : activeWorkspace;
      if (next.id !== activeWorkspace.id) {
        await queryClient.cancelQueries();
        setApiSessionContext({ csrfToken: currentSession.csrf_token, workspaceId: next.id });
        queryClient.clear();
      }
      setCurrentSession({ ...currentSession, workspaces: remaining, active_workspace: next });
      setActiveWorkspace(next);
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

function withStatus(session: IdentitySession, workspaceId: string, status: WorkspaceStatus): IdentitySession {
  const update = (workspace: WorkspaceSummary) => (workspace.id === workspaceId ? { ...workspace, status } : workspace);
  return { ...session, workspaces: session.workspaces.map(update), active_workspace: update(session.active_workspace) };
}

export function useWorkspace(): WorkspaceContextValue | null {
  return useContext(WorkspaceContext);
}
