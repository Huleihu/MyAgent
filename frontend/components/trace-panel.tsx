"use client";

import { useState } from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDurationMs } from "@/lib/format";
import type { ChatTurn, JsonObject, RetrievalTrace } from "@/lib/types";

function isRecord(value: unknown): value is JsonObject { return typeof value === "object" && value !== null && !Array.isArray(value); }

function findRetrievalTrace(turn: ChatTurn): RetrievalTrace | null {
  for (const toolTrace of turn.toolTraces) {
    const value = isRecord(toolTrace.result) ? toolTrace.result.retrieval_trace : null;
    if (toolTrace.tool_name === "retrieval.search" && isRecord(value) && typeof value.query === "string" && typeof value.requested_top_k === "number" && Array.isArray(value.retrieved_chunks) && Array.isArray(value.reranked_chunks) && Array.isArray(value.citations)) return value as unknown as RetrievalTrace;
  }
  return null;
}

/** 仅展示 RetrievalTool 返回的内部可观测摘要，不重新计算 Trace。 */
function RetrievalContent({ trace }: { trace: RetrievalTrace | null }) {
  if (!trace) return <p className="trace-empty">当前工具结果未提供检索轨迹，其他调试信息仍可正常查看。</p>;
  const stages: ReadonlyArray<{ label: string; count: number; durationMs: number }> = [
    { label: "初步召回", count: trace.retrieved_count, durationMs: trace.retrieve_duration_ms },
    { label: "重排结果", count: trace.reranked_count, durationMs: trace.rerank_duration_ms },
    { label: "最终引用", count: trace.citation_count, durationMs: trace.citation_duration_ms },
  ];

  return <section className="trace-summary" role="region" aria-label="检索阶段摘要">
    <div className="trace-query"><span>查询</span><p>{trace.query}</p></div>
    <div className="trace-stage-grid">{stages.map(({ label, count, durationMs }) => <div className="trace-stage" key={label}><span>{label}</span><strong>{count}</strong><small>{formatDurationMs(durationMs)} ms</small></div>)}</div>
    <div className="trace-meta"><span>请求数量 <strong>{trace.requested_top_k}</strong></span><span>总耗时 <strong>{formatDurationMs(trace.total_duration_ms)} ms</strong></span></div>
    <div className="trace-table-wrap"><table><thead><tr><th>排名</th><th>Chunk ID</th><th>文档 ID</th><th>最终分数</th><th>重排分数</th></tr></thead><tbody>{[...trace.retrieved_chunks, ...trace.reranked_chunks].map((chunk, index) => <tr key={`${chunk.chunk_id}-${index}`}><td>{chunk.rank}</td><td>{chunk.chunk_id}</td><td>{chunk.doc_id}</td><td>{chunk.final_score ?? "—"}</td><td>{chunk.rerank_score ?? "—"}</td></tr>)}</tbody></table></div>
  </section>;
}

/** 展示当前回合的节点、工具、检索与原始数据调试视图。 */
export function TracePanel({ turn }: { turn: ChatTurn | null }) {
  const [tab, setTab] = useState("node");
  if (!turn) return <aside className="trace-empty"><span className="empty-orbit" aria-hidden="true" /><p>选择一轮对话查看调试信息</p></aside>;
  const retrieval = findRetrievalTrace(turn);

  return <aside className="trace-panel">
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList className="trace-tabs"><TabsTrigger value="node">节点</TabsTrigger><TabsTrigger value="tool">工具</TabsTrigger><TabsTrigger value="retrieval">检索</TabsTrigger><TabsTrigger value="json">JSON</TabsTrigger></TabsList>
      <TabsContent value="node"><pre className="trace-json">{JSON.stringify(turn.nodeTraces, null, 2)}</pre></TabsContent>
      <TabsContent value="tool"><pre className="trace-json">{JSON.stringify(turn.toolTraces, null, 2)}</pre></TabsContent>
      <TabsContent value="retrieval"><RetrievalContent trace={retrieval} /></TabsContent>
      <TabsContent value="json"><pre className="trace-json">{JSON.stringify(turn, null, 2)}</pre></TabsContent>
    </Tabs>
  </aside>;
}
