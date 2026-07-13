import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CitationPanel } from "@/components/citation-panel";

afterEach(cleanup);
describe("CitationPanel", () => {
  it("opens citation details in an accessible sheet", () => {
    render(<CitationPanel citations={[{ doc_id: "doc-1", chunk_id: "doc-1:0", title: "资料", source: "demo", snippet: "详细摘要", score: 1, metadata: {} }]} />);
    fireEvent.click(screen.getByRole("button", { name: /资料/ }));
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByText("doc-1 / doc-1:0")).toBeTruthy();
  });
});
