import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConsolePage } from "@/components/console-page";
import { useConversationStore } from "@/stores/conversation-store";

const apiMocks = vi.hoisted(() => ({
  createSession: vi.fn(),
  sendMessage: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ agentApi: apiMocks }));

describe("ConsolePage 新建会话", () => {
  beforeEach(() => {
    useConversationStore.getState().reset();
    apiMocks.createSession.mockReset();
  });

  it("创建并自动选中新的会话", async () => {
    apiMocks.createSession.mockResolvedValue({ session_id: "session-new" });
    const user = userEvent.setup();

    render(<ConsolePage />);
    await user.click(screen.getByRole("button", { name: "新建会话" }));

    expect(await screen.findByText(/session-new/)).toBeTruthy();
    expect(apiMocks.createSession).toHaveBeenCalledTimes(1);
    expect(useConversationStore.getState().currentSessionId).toBe("session-new");
  });
});
