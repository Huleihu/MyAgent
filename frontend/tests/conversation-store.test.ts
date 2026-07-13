import { beforeEach, describe, expect, it } from "vitest";

import { useConversationStore } from "@/stores/conversation-store";

describe("conversation store", () => {
  beforeEach(() => useConversationStore.getState().reset());

  it("keeps one failed user turn when retrying the same request", () => {
    const store = useConversationStore.getState();
    store.addSession("session-a");
    const turnId = store.addPendingTurn("session-a", "查询 RAG");
    store.failTurn("session-a", turnId, { code: "network", message: "失败", status: 502 });
    store.retryTurn("session-a", turnId);

    const turns = useConversationStore.getState().turnsBySessionId["session-a"];
    expect(turns).toHaveLength(1);
    expect(turns[0]).toMatchObject({ userInput: "查询 RAG", status: "pending" });
  });

  it("keeps turns isolated by session and selects historical turn", () => {
    const store = useConversationStore.getState();
    store.addSession("session-a");
    store.addSession("session-b");
    const firstTurnId = store.addPendingTurn("session-a", "第一轮");
    store.addPendingTurn("session-b", "另一会话");
    store.selectTurn("session-a", firstTurnId);

    const state = useConversationStore.getState();
    expect(state.turnsBySessionId["session-a"]).toHaveLength(1);
    expect(state.turnsBySessionId["session-b"]).toHaveLength(1);
    expect(state.selectedTurnIdBySessionId["session-a"]).toBe(firstTurnId);
  });
});
