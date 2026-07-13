import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { ChatWorkspace } from "@/components/chat-workspace";
import { TracePanel } from "@/components/trace-panel";
import type { ChatTurn } from "@/lib/types";
import { useConversationStore } from "@/stores/conversation-store";

const turn: ChatTurn = {
  id: "t1",
  userInput: "检索流程是什么？",
  outputText: "这是确定性的检索流程。",
  citations: [],
  nodeTraces: [],
  toolTraces: [{
    trace_id: "r1",
    tool_name: "retrieval.search",
    call_id: "call-1",
    arguments: { query: "检索流程是什么？" },
    success: true,
    error: null,
    duration_ms: 4,
    token_usage: null,
    result: { retrieval_trace: { query: "检索流程是什么？", requested_top_k: 3, retrieved_chunks: [], reranked_chunks: [], citations: [], retrieved_count: 0, reranked_count: 0, citation_count: 0, final_count: 0, retrieve_duration_ms: 1, rerank_duration_ms: 1, citation_duration_ms: 1, total_duration_ms: 4 } },
  }],
  status: "success",
  error: null,
};

describe("控制台内容语义区域", () => {
  beforeEach(() => {
    useConversationStore.getState().reset();
    useConversationStore.getState().addSession("s1");
    const id = useConversationStore.getState().addPendingTurn("s1", turn.userInput);
    useConversationStore.getState().resolveTurn("s1", id, { session_id: "s1", output_text: turn.outputText ?? "", citations: [], node_traces: [], tool_traces: turn.toolTraces });
  });

  it("为聊天记录提供语义区域", () => {
    render(<QueryClientProvider client={new QueryClient()}><ChatWorkspace /></QueryClientProvider>);

    expect(screen.getByRole("region", { name: "聊天记录" })).toBeTruthy();
  });

  it("为检索阶段提供语义区域", async () => {
    const user = userEvent.setup();
    render(<TracePanel turn={turn} />);
    await user.click(screen.getByRole("tab", { name: "检索" }));

    expect(screen.getByRole("region", { name: "检索阶段摘要" })).toBeTruthy();
  });
});
