import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatWorkspace } from "@/components/chat-workspace";
import { useConversationStore } from "@/stores/conversation-store";

const apiMocks = vi.hoisted(() => ({ sendMessage: vi.fn(), createSession: vi.fn() }));
vi.mock("@/lib/api", () => ({ agentApi: apiMocks }));
describe("ChatWorkspace", () => { beforeEach(() => { useConversationStore.getState().reset(); apiMocks.sendMessage.mockReset(); }); it("sends one turn and renders the returned answer", async () => { useConversationStore.getState().addSession("s1"); apiMocks.sendMessage.mockResolvedValue({ session_id: "s1", output_text: "回答", citations: [], node_traces: [], tool_traces: [] }); render(<QueryClientProvider client={new QueryClient()}><ChatWorkspace /></QueryClientProvider>); fireEvent.change(screen.getByLabelText("消息输入"), { target: { value: "问题" } }); fireEvent.click(screen.getByRole("button", { name: "发送" })); expect(await screen.findByText(/回答/)).toBeTruthy(); expect(apiMocks.sendMessage).toHaveBeenCalledTimes(1); }); });
