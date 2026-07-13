import { proxy } from "@/app/api/sessions/route";
export async function POST(request: Request, context: { params: Promise<{ sessionId: string }> }) { const { sessionId } = await context.params; const body = await request.text(); return proxy(`/sessions/${encodeURIComponent(sessionId)}/messages`, { method: "POST", body }); }
