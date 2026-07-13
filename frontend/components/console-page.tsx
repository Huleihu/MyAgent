"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useMemo } from "react";
import { ChatWorkspace } from "@/components/chat-workspace";
import { CitationPanel } from "@/components/citation-panel";
import { TracePanel } from "@/components/trace-panel";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useConversationStore } from "@/stores/conversation-store";

function SessionList() { const sessionId = useConversationStore((state) => state.currentSessionId); const turns = useConversationStore((state) => sessionId ? state.turnsBySessionId[sessionId] ?? [] : []); const selectTurn = useConversationStore((state) => state.selectTurn); return <section><h2>会话</h2><p>{sessionId ?? "未选择会话"}</p>{turns.map((turn) => <button key={turn.id} onClick={() => sessionId && selectTurn(sessionId, turn.id)}>{turn.userInput}</button>)}</section>; }
function ConsoleContent() { const sessionId = useConversationStore((state) => state.currentSessionId); const turns = useConversationStore((state) => sessionId ? state.turnsBySessionId[sessionId] ?? [] : []); const selectedId = useConversationStore((state) => sessionId ? state.selectedTurnIdBySessionId[sessionId] : null); const turn = turns.find((item) => item.id === selectedId) ?? turns.at(-1) ?? null; return <main className="min-h-screen md:grid md:grid-cols-[16rem_minmax(0,1fr)_28rem]"><div className="flex gap-2 border-b p-3 md:hidden"><Sheet><SheetTrigger>会话</SheetTrigger><SheetContent><SheetTitle>会话</SheetTitle><SessionList /></SheetContent></Sheet><Sheet><SheetTrigger>Trace</SheetTrigger><SheetContent><SheetTitle>Trace</SheetTitle><TracePanel turn={turn} /></SheetContent></Sheet></div><aside className="hidden border-r p-4 md:block"><SessionList /></aside><section className="min-w-0 p-4"><ChatWorkspace />{turn && <CitationPanel citations={turn.citations} />}</section><aside className="hidden border-l p-4 md:block"><TracePanel turn={turn} /></aside></main>; }
export function ConsolePage() { const client = useMemo(() => new QueryClient(), []); return <QueryClientProvider client={client}><ConsoleContent /></QueryClientProvider>; }
