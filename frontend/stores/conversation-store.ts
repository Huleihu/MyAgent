import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import type { ApiError, ChatResponse, ChatTurn } from "@/lib/types";

type ConversationState = {
  sessionIds: string[];
  currentSessionId: string | null;
  turnsBySessionId: Record<string, ChatTurn[]>;
  selectedTurnIdBySessionId: Record<string, string | null>;
  addSession: (sessionId: string) => void;
  selectSession: (sessionId: string) => void;
  addPendingTurn: (sessionId: string, userInput: string) => string;
  resolveTurn: (sessionId: string, turnId: string, response: ChatResponse) => void;
  failTurn: (sessionId: string, turnId: string, error: ApiError) => void;
  retryTurn: (sessionId: string, turnId: string) => void;
  selectTurn: (sessionId: string, turnId: string) => void;
  reset: () => void;
};

const initialState: Pick<ConversationState, "sessionIds" | "currentSessionId" | "turnsBySessionId" | "selectedTurnIdBySessionId"> = { sessionIds: [], currentSessionId: null, turnsBySessionId: {}, selectedTurnIdBySessionId: {} };
/** 空会话时复用稳定引用，避免 React 外部状态快照重复触发更新。 */
export const EMPTY_CHAT_TURNS: ChatTurn[] = [];
const updateTurn = (turns: ChatTurn[], turnId: string, update: Partial<ChatTurn>) => turns.map((turn) => turn.id === turnId ? { ...turn, ...update } : turn);
const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);

export function parsePersistedConversation(value: unknown): typeof initialState | null {
  if (!isRecord(value) || !Array.isArray(value.sessionIds) || !value.sessionIds.every((id) => typeof id === "string") || (value.currentSessionId !== null && typeof value.currentSessionId !== "string") || !isRecord(value.turnsBySessionId)) return null;
  const sessionIds = value.sessionIds;
  if (value.currentSessionId !== null && !sessionIds.includes(value.currentSessionId)) return null;
  const turnsBySessionId = value.turnsBySessionId as Record<string, unknown>;
  if (!sessionIds.every((id) => Array.isArray(turnsBySessionId[id]))) return null;
  const selected = isRecord(value.selectedTurnIdBySessionId) ? value.selectedTurnIdBySessionId : {};
  const selectedTurnIdBySessionId: Record<string, string | null> = {};
  for (const id of sessionIds) { const selectedId = selected[id]; if (selectedId !== undefined && selectedId !== null && typeof selectedId !== "string") return null; selectedTurnIdBySessionId[id] = typeof selectedId === "string" ? selectedId : null; }
  return { sessionIds, currentSessionId: value.currentSessionId, turnsBySessionId: turnsBySessionId as Record<string, ChatTurn[]>, selectedTurnIdBySessionId };
}

export const useConversationStore = create<ConversationState>()(persist((set) => ({
  ...initialState,
  addSession: (sessionId) => set((state) => ({ sessionIds: state.sessionIds.includes(sessionId) ? state.sessionIds : [...state.sessionIds, sessionId], currentSessionId: sessionId, turnsBySessionId: { ...state.turnsBySessionId, [sessionId]: state.turnsBySessionId[sessionId] ?? [] }, selectedTurnIdBySessionId: { ...state.selectedTurnIdBySessionId, [sessionId]: null } })),
  selectSession: (sessionId) => set({ currentSessionId: sessionId }),
  addPendingTurn: (sessionId, userInput) => { const id = crypto.randomUUID(); set((state) => { const turn: ChatTurn = { id, userInput, outputText: null, citations: [], nodeTraces: [], toolTraces: [], status: "pending", error: null }; return { turnsBySessionId: { ...state.turnsBySessionId, [sessionId]: [...(state.turnsBySessionId[sessionId] ?? []), turn] }, selectedTurnIdBySessionId: { ...state.selectedTurnIdBySessionId, [sessionId]: id } }; }); return id; },
  resolveTurn: (sessionId, turnId, response) => set((state) => ({ turnsBySessionId: { ...state.turnsBySessionId, [sessionId]: updateTurn(state.turnsBySessionId[sessionId] ?? [], turnId, { outputText: response.output_text, citations: response.citations, nodeTraces: response.node_traces, toolTraces: response.tool_traces, status: "success", error: null }) } })),
  failTurn: (sessionId, turnId, error) => set((state) => ({ turnsBySessionId: { ...state.turnsBySessionId, [sessionId]: updateTurn(state.turnsBySessionId[sessionId] ?? [], turnId, { status: "error", error }) } })),
  retryTurn: (sessionId, turnId) => set((state) => ({ turnsBySessionId: { ...state.turnsBySessionId, [sessionId]: updateTurn(state.turnsBySessionId[sessionId] ?? [], turnId, { status: "pending", error: null }) }, selectedTurnIdBySessionId: { ...state.selectedTurnIdBySessionId, [sessionId]: turnId } })),
  selectTurn: (sessionId, turnId) => set((state) => ({ selectedTurnIdBySessionId: { ...state.selectedTurnIdBySessionId, [sessionId]: turnId } })),
  reset: () => set(initialState),
}), { name: "myagent-conversations", storage: createJSONStorage(() => localStorage), partialize: (state) => ({ sessionIds: state.sessionIds, currentSessionId: state.currentSessionId, turnsBySessionId: state.turnsBySessionId, selectedTurnIdBySessionId: state.selectedTurnIdBySessionId }), merge: (persisted, current) => ({ ...current, ...(parsePersistedConversation(persisted) ?? initialState) }) }));
