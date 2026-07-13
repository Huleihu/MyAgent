"use client";

import { useMutation } from "@tanstack/react-query";
import { FormEvent, useState } from "react";

import { agentApi } from "@/lib/api";
import type { ApiError, ChatTurn } from "@/lib/types";
import { EMPTY_CHAT_TURNS, useConversationStore } from "@/stores/conversation-store";

function toApiError(error: unknown): ApiError {
  return { code: "request_failed", message: error instanceof Error ? error.message : "请求失败", status: 502 };
}

/** 负责当前会话的消息发送、重试与回合呈现。 */
export function ChatWorkspace() {
  const [input, setInput] = useState("");
  const sessionId = useConversationStore((state) => state.currentSessionId);
  const turns = useConversationStore((state) => sessionId ? state.turnsBySessionId[sessionId] ?? EMPTY_CHAT_TURNS : EMPTY_CHAT_TURNS);
  const addPendingTurn = useConversationStore((state) => state.addPendingTurn);
  const resolveTurn = useConversationStore((state) => state.resolveTurn);
  const failTurn = useConversationStore((state) => state.failTurn);
  const retryTurn = useConversationStore((state) => state.retryTurn);
  const mutation = useMutation({
    mutationFn: ({ id, text }: { id: string; text: string }) => sessionId
      ? agentApi.sendMessage(sessionId, { user_input: text }).then((response) => ({ id, response }))
      : Promise.reject(new Error("请先创建会话")),
    onSuccess: ({ id, response }) => { if (sessionId) resolveTurn(sessionId, id, response); },
    onError: (error, variables) => { if (sessionId) failTurn(sessionId, variables.id, toApiError(error)); },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = input.trim();
    if (!sessionId || !text || mutation.isPending) return;
    const id = addPendingTurn(sessionId, text);
    setInput("");
    mutation.mutate({ id, text });
  };
  const retry = (turn: ChatTurn) => {
    if (!sessionId || mutation.isPending) return;
    retryTurn(sessionId, turn.id);
    mutation.mutate({ id: turn.id, text: turn.userInput });
  };

  if (!sessionId) return <section className="empty-workspace"><span className="empty-orbit" aria-hidden="true" /><p className="eyebrow">准备就绪</p><h3>创建一个会话开始探索</h3><p>发送问题后，这里会展示回答、引用和完整执行轨迹。</p></section>;

  return <section className="chat-workspace">
    <div className="chat-timeline" role="region" aria-label="聊天记录">
      {turns.map((turn) => <article className="chat-turn" key={turn.id}>
        <div className="user-message"><span className="message-label">你</span><p>{turn.userInput}</p></div>
        {turn.outputText && <div className="agent-message"><div className="agent-message-header"><span className="agent-dot" aria-hidden="true" /><span>Hul 的 Agent</span></div><p>{turn.outputText}</p></div>}
        {turn.status === "pending" && <div className="pending-message"><span className="pending-pulse" aria-hidden="true" />正在执行工具与检索流程…</div>}
        {turn.status === "error" && <div className="failed-message"><span>{turn.error?.message ?? "请求失败"}</span><button onClick={() => retry(turn)}>重新发送</button></div>}
      </article>)}
    </div>
    <form className="message-composer" onSubmit={submit}>
      <label className="sr-only" htmlFor="message-input">消息输入</label>
      <textarea id="message-input" aria-label="消息输入" placeholder="输入问题，开始一次可观测的 Agent 对话…" value={input} onChange={(event) => setInput(event.target.value)} />
      <div className="composer-footer"><span>Enter 发送 · Shift + Enter 换行</span><button type="submit" disabled={mutation.isPending || !input.trim()}>{mutation.isPending ? "执行中…" : "发送"}</button></div>
    </form>
  </section>;
}
