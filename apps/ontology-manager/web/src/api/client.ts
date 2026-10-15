/** Typed data hooks over /api. */

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { AgentTool, ObjectDetail, ObjectList, OntologySchema, Profile, SqlResult, Workflow } from "./types";

type Params = Record<string, string | number | boolean | null | undefined | string[]>;

export async function getJson<T>(path: string, params: Params = {}): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v == null || v === "") continue;
    if (Array.isArray(v)) v.forEach((item) => qs.append(k, item));
    else qs.set(k, String(v));
  }
  const res = await fetch(`/api${path}${qs.size ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${(await res.text()).slice(0, 300)}`);
  return res.json() as Promise<T>;
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
  }
  return res.json() as Promise<T>;
}

export const useOntology = () =>
  useQuery({ queryKey: ["ontology"], queryFn: () => getJson<OntologySchema>("/ontology"), staleTime: Infinity });

export const useObjects = (type: string | null, params: { q?: string; filter?: string[]; order_by?: string; desc?: boolean }) =>
  useQuery({
    queryKey: ["objects", type, params],
    queryFn: () => getJson<ObjectList>(`/objects/${type}`, { ...params, limit: 5000 }),
    enabled: !!type,
    placeholderData: keepPreviousData,
  });

export const useObject = (type: string | null, pk: string | null) =>
  useQuery({
    queryKey: ["object", type, pk],
    queryFn: () => getJson<ObjectDetail>(`/objects/${type}/${encodeURIComponent(pk ?? "")}`),
    enabled: !!type && pk != null,
  });

export const useProfile = (type: string) =>
  useQuery({ queryKey: ["profile", type], queryFn: () => getJson<Profile>(`/objects/${type}/profile`), staleTime: Infinity });

export const useWorkflows = () => useQuery({ queryKey: ["workflows"], queryFn: () => getJson<{ file: string; workflows: Workflow[] }>("/workflows") });
export const useAgentTools = () => useQuery({ queryKey: ["agent-tools"], queryFn: () => getJson<AgentTool[]>("/agent/tools"), staleTime: Infinity });
export const useAgentContext = () => useQuery({ queryKey: ["agent-context"], queryFn: () => getJson<{ markdown: string }>("/agent/context"), staleTime: Infinity });

export const useSql = () => useMutation({ mutationFn: (sql: string) => postJson<SqlResult>("/sql", { sql, limit: 5000 }) });

export const useAgentCall = () =>
  useMutation({
    mutationFn: (body: { tool: string; args: Record<string, unknown>; confirm?: boolean }) => postJson<{ tool: string; result: unknown }>("/agent/call", body),
  });

/** Run an ontology action (the only write path). Refreshes everything that reads write-back objects. */
export function useApplyAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, params }: { name: string; params: Record<string, unknown> }) =>
      postJson<{ action: string; object_type: string; primary_key: string; object: Record<string, unknown> }>(`/actions/${name}`, params),
    onSuccess: () => {
      for (const key of ["objects", "object", "ontology", "profile"]) qc.invalidateQueries({ queryKey: [key] });
    },
  });
}

export type ManagerState = { revision: string; overrides: number; changes: number; schema_file: string; edit_store: string };
export type ChangeEntry = { id: number; created_at: string; kind: string; object_type: string; primary_key: string | null; before: Record<string, unknown>; after: Record<string, unknown> };
export type EditContext = { object: Record<string, unknown>; base: Record<string, unknown>; overrides: Record<string, unknown>; protected: string[] };
export type LineageNode = { id: string; label: string; layer: string; available: boolean; path?: string; object_type?: string };
export type LineageGraph = { nodes: LineageNode[]; edges: { source: string; target: string; kind: string }[]; basis: string };
export const useManagerState = () => useQuery({ queryKey: ["manager"], queryFn: () => getJson<ManagerState>("/management/state") });
export const useHistory = () => useQuery({ queryKey: ["history"], queryFn: () => getJson<{ entries: ChangeEntry[] }>("/management/history") });
export const useLineage = () => useQuery({ queryKey: ["lineage"], queryFn: () => getJson<LineageGraph>("/management/lineage") });
export const useEditContext = (type: string, pk: string) => useQuery({ queryKey: ["edit-context", type, pk], queryFn: () => getJson<EditContext>(`/management/objects/${encodeURIComponent(type)}/${encodeURIComponent(pk)}`) });
export function useManagerSave() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ path, body }: { path: string; body: unknown }) => postJson(`/management${path}`, body),
    onSuccess: () => qc.invalidateQueries(),
  });
}
