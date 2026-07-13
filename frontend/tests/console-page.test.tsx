import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ConsolePage } from "@/components/console-page";
import { useConversationStore } from "@/stores/conversation-store";

const response = (text: string, title: string, query: string) => ({
  session_id: "s1",
  output_text: text,
  citations: [{ doc_id: title, chunk_id: `${title}:0`, title, source: "demo", snippet: `${title} 摘要`, score: 1, metadata: {} }],
  node_traces: [],
  tool_traces: [{
    trace_id: query,
    tool_name: "retrieval.search",
    call_id: query,
    arguments: { query },
    success: true,
    error: null,
    duration_ms: 1,
    token_usage: null,
    result: { retrieval_trace: { query, requested_top_k: 3, retrieved_chunks: [], reranked_chunks: [], citations: [], retrieved_count: 0, reranked_count: 0, citation_count: 0, final_count: 0, retrieve_duration_ms: 0, rerank_duration_ms: 0, citation_duration_ms: 0, total_duration_ms: 0 } },
  }],
});

describe("ConsolePage", () => {
  beforeEach(() => {
    const store = useConversationStore.getState();
    store.reset();
    store.addSession("s1");
    const first = store.addPendingTurn("s1", "第一轮问题");
    store.resolveTurn("s1", first, response("第一轮回答", "第一篇", "第一轮问题"));
    const second = store.addPendingTurn("s1", "第二轮问题");
    store.resolveTurn("s1", second, response("第二轮回答", "第二篇", "第二轮问题"));
  });

  afterEach(cleanup);

  it("切换历史回合时同步切换引用和检索轨迹", async () => {
    const user = userEvent.setup();
    render(<ConsolePage />);

    expect(screen.getByText("第二篇")).toBeTruthy();
    await user.click(screen.getByRole("tab", { name: "检索" }));
    expect(screen.getAllByText(/第二轮问题/).length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /第一轮问题$/ }));
    expect(screen.getByText("第一篇")).toBeTruthy();
    expect(screen.getAllByText(/第一轮问题/).length).toBeGreaterThan(0);
  });

  it("空状态不会触发外部状态快照循环", () => {
    useConversationStore.getState().reset();
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);

    try {
      render(<ConsolePage />);
      expect(screen.getByText("等待创建会话")).toBeTruthy();
      expect(consoleError).not.toHaveBeenCalled();
    } finally {
      consoleError.mockRestore();
    }
  });
});
