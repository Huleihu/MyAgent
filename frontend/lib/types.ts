export type JsonObject = Record<string, unknown>;

export interface Citation { doc_id: string; chunk_id: string; source: string; title: string; snippet: string; score: number; metadata: JsonObject; }
export interface NodeTrace { node_id: string; node_type: string; inputs: JsonObject; output: JsonObject | null; success: boolean; error: JsonObject | null; duration_ms: number; }
export interface RetrievalChunkTrace { chunk_id: string; doc_id: string; rank: number; keyword_score: number | null; vector_score: number | null; final_score: number | null; rerank_score: number | null; }
export interface RetrievalCitationTrace { chunk_id: string; doc_id: string; rank: number; score: number; }
export interface RetrievalTrace { query: string; requested_top_k: number; retrieved_chunks: RetrievalChunkTrace[]; reranked_chunks: RetrievalChunkTrace[]; citations: RetrievalCitationTrace[]; retrieved_count: number; reranked_count: number; citation_count: number; final_count: number; retrieve_duration_ms: number; rerank_duration_ms: number; citation_duration_ms: number; total_duration_ms: number; }
export interface ToolTrace { trace_id: string; tool_name: string; call_id: string | null; arguments: JsonObject; success: boolean; result: JsonObject | null; error: JsonObject | null; duration_ms: number; token_usage: JsonObject | null; }
export interface ChatRequest { user_input: string; }
export interface ChatResponse { session_id: string; output_text: string; citations: Citation[]; node_traces: NodeTrace[]; tool_traces: ToolTrace[]; }
export interface ApiError { code: string; message: string; status: number; }
export type ChatTurnStatus = "pending" | "success" | "error";
export interface ChatTurn { id: string; userInput: string; outputText: string | null; citations: Citation[]; nodeTraces: NodeTrace[]; toolTraces: ToolTrace[]; status: ChatTurnStatus; error: ApiError | null; }
