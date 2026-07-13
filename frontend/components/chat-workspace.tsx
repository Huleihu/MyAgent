"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { agentApi } from "@/lib/api";
import type { ApiError, ChatTurn } from "@/lib/types";
import { useConversationStore } from "@/stores/conversation-store";

function toApiError(error: unknown): ApiError { return { code: "request_failed", message: error instanceof Error ? error.message : "请求失败", status: 502 }; }
export function ChatWorkspace() {
  const [input, setInput] = useState("");
  const sessionId = useConversationStore((state) => state.currentSessionId);
  const turns = useConversationStore((state) => sessionId ? state.turnsBySessionId[sessionId] ?? [] : []);
  const addPendingTurn = useConversationStore((state) => state.addPendingTurn);
  const resolveTurn = useConversationStore((state) => state.resolveTurn);
  const failTurn = useConversationStore((state) => state.failTurn);
  const retryTurn = useConversationStore((state) => state.retryTurn);
  const mutation = useMutation({ mutationFn: ({ id, text }: { id: string; text: string }) => sessionId ? agentApi.sendMessage(sessionId, { user_input: text }).then((response) => ({ id, response })) : Promise.reject(new Error("请先创建会话")), onSuccess: ({ id, response }) => { if (sessionId) resolveTurn(sessionId, id, response); }, onError: (error, variables) => { if (sessionId) failTurn(sessionId, variables.id, toApiError(error)); } });
  const submit = () => { const text = input.trim(); if (!sessionId || !text || mutation.isPending) return; const id = addPendingTurn(sessionId, text); setInput(""); mutation.mutate({ id, text }); };
  const retry = (turn: ChatTurn) => { if (!sessionId || mutation.isPending) return; retryTurn(sessionId, turn.id); mutation.mutate({ id: turn.id, text: turn.userInput }); };
  if (!sessionId) return <section><p>请先创建会话</p></section>;
  return <section><div>{turns.map((turn) => <article key={turn.id}><p>你：{turn.userInput}</p>{turn.outputText && <p>Agent：{turn.outputText}</p>}{turn.status === "pending" && <p>发送中…</p>}{turn.status === "error" && <button onClick={() => retry(turn)}>重试</button>}</article>)}</div><label>消息输入<textarea aria-label="消息输入" value={input} onChange={(event) => setInput(event.target.value)} /></label><button onClick={submit} disabled={mutation.isPending || !input.trim()}>发送</button></section>;
}
