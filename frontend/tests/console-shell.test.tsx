import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { ConsolePage } from "@/components/console-page";
import { useConversationStore } from "@/stores/conversation-store";

describe("深色工程控制台框架", () => {
  beforeEach(() => {
    useConversationStore.getState().reset();
  });

  it("提供品牌栏和命名的桌面侧栏", () => {
    render(<ConsolePage />);

    expect(screen.getByRole("banner", { name: "Hul 的 Agent 控制台" })).toBeTruthy();
    expect(screen.getByRole("complementary", { name: "会话列表" })).toBeTruthy();
    expect(screen.getByRole("complementary", { name: "调试面板" })).toBeTruthy();
  });
});
