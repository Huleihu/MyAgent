import type { ChatRequest, ChatResponse } from "@/lib/types";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof body === "object" && body !== null && "detail" in body ? String(body.detail) : "请求失败");
  return body as T;
}
export const agentApi = { createSession: () => requestJson<{ session_id: string }>("/api/sessions", { method: "POST" }), sendMessage: (sessionId: string, request: ChatRequest) => requestJson<ChatResponse>(`/api/sessions/${encodeURIComponent(sessionId)}/messages`, { method: "POST", body: JSON.stringify(request) }) };
