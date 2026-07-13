"use client";

import { QueryClient, QueryClientProvider, useMutation } from "@tanstack/react-query";
import { useMemo } from "react";

import { ChatWorkspace } from "@/components/chat-workspace";
import { CitationPanel } from "@/components/citation-panel";
import { TracePanel } from "@/components/trace-panel";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { agentApi } from "@/lib/api";
import { EMPTY_CHAT_TURNS, useConversationStore } from "@/stores/conversation-store";

/** 会话导航只负责创建、选择和展示浏览器本地会话目录。 */
function SessionList() {
  const sessionId = useConversationStore((state) => state.currentSessionId);
  const turns = useConversationStore((state) => sessionId ? state.turnsBySessionId[sessionId] ?? EMPTY_CHAT_TURNS : EMPTY_CHAT_TURNS);
  const selectTurn = useConversationStore((state) => state.selectTurn);
  const addSession = useConversationStore((state) => state.addSession);
  const createSession = useMutation({
    mutationFn: agentApi.createSession,
    onSuccess: ({ session_id }) => addSession(session_id),
  });
  const errorMessage = createSession.error instanceof Error ? createSession.error.message : null;

  return <section className="session-panel">
    <div className="panel-heading">
      <div>
        <p className="eyebrow">本地目录</p>
        <h2>会话</h2>
      </div>
      <span className="session-count">{turns.length}</span>
    </div>
    <button className="primary-action" onClick={() => createSession.mutate()} disabled={createSession.isPending}>
      <span aria-hidden="true">＋</span>
      {createSession.isPending ? "正在创建…" : "新建会话"}
    </button>
    {errorMessage && <p className="inline-error" role="alert">创建会话失败：{errorMessage}</p>}
    <div className="session-status">
      <span className="status-dot" aria-hidden="true" />
      <span>{sessionId ? "当前会话" : "等待创建会话"}</span>
    </div>
    {sessionId && <p className="session-id" title={sessionId}>{sessionId}</p>}
    <div className="turn-list" aria-label="当前会话历史">
      {turns.length === 0 && <p className="empty-note">创建后输入问题，回合会显示在这里。</p>}
      {turns.map((turn, index) => <button className="turn-button" key={turn.id} onClick={() => sessionId && selectTurn(sessionId, turn.id)}>
        <span className="turn-index">{String(index + 1).padStart(2, "0")}</span>
        <span>{turn.userInput}</span>
      </button>)}
    </div>
  </section>;
}

/** 组合桌面三栏与小屏抽屉，不承担会话或检索业务逻辑。 */
function ConsoleContent() {
  const sessionId = useConversationStore((state) => state.currentSessionId);
  const turns = useConversationStore((state) => sessionId ? state.turnsBySessionId[sessionId] ?? EMPTY_CHAT_TURNS : EMPTY_CHAT_TURNS);
  const selectedId = useConversationStore((state) => sessionId ? state.selectedTurnIdBySessionId[sessionId] : null);
  const turn = turns.find((item) => item.id === selectedId) ?? turns.at(-1) ?? null;

  return <main className="console-shell">
    <header aria-label="Hul 的 Agent 控制台" className="console-header">
      <div className="brand-lockup">
        <span className="brand-mark" aria-hidden="true">H</span>
        <div>
          <p className="eyebrow">智能体可观测性</p>
          <h1>Hul 的 Agent</h1>
        </div>
      </div>
      <div className="runtime-status">
        <span className="status-dot" aria-hidden="true" />
        <span>运行服务已连接</span>
        <span className="status-divider" aria-hidden="true" />
        <span className="status-mono">{sessionId ? "会话进行中" : "准备就绪"}</span>
      </div>
    </header>

    <div className="mobile-console-nav">
      <Sheet>
        <SheetTrigger>会话</SheetTrigger>
        <SheetContent><SheetTitle>会话</SheetTitle><SessionList /></SheetContent>
      </Sheet>
      <Sheet>
        <SheetTrigger>调试信息</SheetTrigger>
        <SheetContent><SheetTitle>调试信息</SheetTitle><TracePanel turn={turn} /></SheetContent>
      </Sheet>
    </div>

    <div className="console-layout">
      <aside aria-label="会话列表" className="console-sidebar session-sidebar"><SessionList /></aside>
      <section className="console-main">
        <div className="workspace-heading">
          <div>
            <p className="eyebrow">对话工作区</p>
            <h2>{sessionId ? "当前会话" : "开始一次新对话"}</h2>
          </div>
          <span className="workspace-badge">确定性 RAG</span>
        </div>
        <ChatWorkspace />
        {turn && <CitationPanel citations={turn.citations} />}
      </section>
      <aside aria-label="调试面板" className="console-sidebar trace-sidebar">
        <div className="panel-heading trace-heading"><div><p className="eyebrow">调试视图</p><h2>执行轨迹</h2></div><span className="live-label">实时</span></div>
        <TracePanel turn={turn} />
      </aside>
    </div>
  </main>;
}

/** 提供每个页面实例独立的 QueryClient。 */
export function ConsolePage() {
  const client = useMemo(() => new QueryClient(), []);
  return <QueryClientProvider client={client}><ConsoleContent /></QueryClientProvider>;
}
