import { afterEach, describe, expect, it, vi } from "vitest";
import { proxy } from "@/app/api/sessions/route";

describe("session BFF proxy", () => {
  afterEach(() => { vi.unstubAllGlobals(); delete process.env.AGENT_API_BASE_URL; });

  it("preserves a backend session-not-found 404 response", async () => {
    process.env.AGENT_API_BASE_URL = "http://agent.test";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "session not found" }), { status: 404 })));

    const response = await proxy("/sessions/missing/messages", { method: "POST" });

    expect(response.status).toBe(404);
    await expect(response.json()).resolves.toEqual({ detail: "session not found" });
  });
});
