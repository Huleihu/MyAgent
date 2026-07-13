import { describe, expect, it } from "vitest";
import { parsePersistedConversation } from "@/stores/conversation-store";

describe("conversation persistence", () => {
  it("drops invalid persisted data instead of restoring it", () => {
    expect(parsePersistedConversation({ sessionIds: [1], currentSessionId: "s1" })).toBeNull();
  });

  it("accepts old session data without selected-turn fields", () => {
    expect(parsePersistedConversation({ sessionIds: ["s1"], currentSessionId: "s1", turnsBySessionId: { s1: [] } })).toEqual({ sessionIds: ["s1"], currentSessionId: "s1", turnsBySessionId: { s1: [] }, selectedTurnIdBySessionId: { s1: null } });
  });
});
