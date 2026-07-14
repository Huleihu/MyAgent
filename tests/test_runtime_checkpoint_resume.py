"""本文件负责验证 SQLite 跨 Runtime 的 Checkpoint 恢复闭环。"""
import unittest
from pathlib import Path
from uuid import uuid4

from my_agent.agent_loop.planner import FinalAnswerAction, Planner, ToolAction
from my_agent.agent_loop.react import ReActAgentLoop
from my_agent.runtime.conversation import ConversationRuntime, RunAlreadyCompletedError
from my_agent.runtime.executor import RuntimeExecutor
from my_agent.runtime.graph import RuntimeGraph
from my_agent.runtime.node_runner import AgentLoopNodeRunner, BeginNodeRunner, MessageNodeRunner
from my_agent.dsl.loader import WorkflowLoader
from my_agent.state.session import SessionState
from my_agent.state.recorder import TraceRecorder
from my_agent.state.sqlite_checkpoint_store import SQLiteCheckpointStore
from my_agent.tools.executor import ToolExecutor
from my_agent.tools.function_tool import FunctionTool
from my_agent.tools.registry import ToolRegistry


class HistoryPlanner(Planner):
    def __init__(self, counts): self.calls = 0; self.counts = counts
    def plan(self, user_input, session):
        self.calls += 1
        names = [item.tool_name for item in session.list_tool_traces()]
        if "tool_a" not in names: return ToolAction("tool_a", {})
        if "tool_b" not in names: return ToolAction("tool_b", {})
        return FinalAnswerAction("完成")

class StopAfterAPlanner(HistoryPlanner):
    def plan(self, user_input, session):
        if any(item.tool_name == "tool_a" for item in session.list_tool_traces()):
            raise RuntimeError("simulate shutdown")
        return super().plan(user_input, session)

def build_runtime(session, store, planner, counts):
    registry = ToolRegistry()
    for name in ("tool_a", "tool_b"):
        registry.register(FunctionTool(name=name, description=name, parameters={"type":"object","properties":{}}, func=lambda arguments, n=name: {"tool": n, "count": counts.__setitem__(n, counts[n]+1) or counts[n]}))
    loop = ReActAgentLoop(planner, ToolExecutor(registry, TraceRecorder(session)), session)
    workflow = WorkflowLoader().load_dict({"workflow_id":"checkpoint-test","nodes":[{"node_id":"begin","node_type":"begin"},{"node_id":"agent","node_type":"agent_loop","inputs":{"user_input":"{{user_input}}"}},{"node_id":"message","node_type":"message","inputs":{"content":"{{agent.output}}"}}],"edges":[{"source":"begin","target":"agent"},{"source":"agent","target":"message"}]})
    return ConversationRuntime(RuntimeExecutor(RuntimeGraph(workflow), {"begin":BeginNodeRunner(),"agent_loop":AgentLoopNodeRunner(loop),"message":MessageNodeRunner()}), session, store, workflow.workflow_id)

class RuntimeCheckpointResumeTest(unittest.TestCase):
    def setUp(self): self.path = Path.cwd() / f"runtime-checkpoint-{uuid4().hex}.db"
    def tearDown(self):
        if self.path.exists(): self.path.unlink(missing_ok=True)
    def test_sqlite_cross_runtime_resume_skips_completed_tool(self):
        counts = {"tool_a":0,"tool_b":0}; store = SQLiteCheckpointStore(self.path); session = SessionState("s1")
        first = build_runtime(session, store, StopAfterAPlanner(counts), counts)
        with self.assertRaises(RuntimeError): first.start("go")
        checkpoint = store.get_latest(next(iter([row[0] for row in store._connection.execute("SELECT run_id FROM checkpoints LIMIT 1")])))
        run_id = checkpoint.run_state.run_id; store.close()
        new_store = SQLiteCheckpointStore(self.path); new_session = SessionState("s1"); planner = HistoryPlanner(counts)
        result = build_runtime(new_session, new_store, planner, counts).resume(run_id)
        self.assertEqual(result.output_text, "完成"); self.assertEqual(counts, {"tool_a":1,"tool_b":1}); self.assertGreater(planner.calls, 0)
        with self.assertRaises(RunAlreadyCompletedError): build_runtime(new_session, new_store, HistoryPlanner(counts), counts).resume(run_id)
        new_store.close()

    def test_pending_tool_resume_executes_before_new_planner_call(self):
        counts = {"tool_a": 0, "tool_b": 0}
        store = SQLiteCheckpointStore(self.path)
        session = SessionState("s1")
        runtime = build_runtime(session, store, HistoryPlanner(counts), counts)
        run_id = "pending-run"
        from my_agent.state.run_state import ExecutionCursor, PendingToolCall, RunState, RunStatus
        from my_agent.state.checkpoint import Checkpoint
        state = RunState(run_id=run_id, session_id="s1", workflow_id="checkpoint-test", status=RunStatus.RUNNING, user_input="go", messages=[], cursor=ExecutionCursor(next_node_id="agent", completed_node_ids=["begin"], agent_round_index=1, agent_phase="tool_pending"), pending_tool_call=PendingToolCall("tool_a", {}, "pending-call"))
        store.save(Checkpoint.create(state)); store.close()
        new_store = SQLiteCheckpointStore(self.path); planner = HistoryPlanner(counts)
        result = build_runtime(SessionState("s1"), new_store, planner, counts).resume(run_id)
        self.assertEqual(result.output_text, "完成")
        self.assertEqual(counts["tool_a"], 1)
        self.assertGreater(planner.calls, 0)
        self.assertEqual(planner.calls, 2)
        new_store.close()


if __name__ == "__main__": unittest.main()
