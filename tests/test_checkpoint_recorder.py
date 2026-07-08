"""
本文件负责验证 CheckpointRecorder 的内存快照记录行为。
本文件不测试文件持久化、数据库存储或 Agent Loop 恢复。
"""

import unittest

from my_agent.state.checkpoint_recorder import CheckpointRecorder
from my_agent.state.session import SessionState


class CheckpointRecorderTest(unittest.TestCase):
    def test_record_creates_checkpoint_with_metadata(self):
        session = SessionState(session_id="session-1")
        session.add_message(role="user", content="你好")
        recorder = CheckpointRecorder(session)

        checkpoint = recorder.record(
            metadata={"reason": "after_user_input", "round_index": 0}
        )

        self.assertEqual(checkpoint.session_id, "session-1")
        self.assertEqual(checkpoint.metadata["reason"], "after_user_input")
        self.assertEqual(checkpoint.metadata["round_index"], 0)
        self.assertEqual(checkpoint.list_messages()[0].content, "你好")
        self.assertEqual(recorder.list_checkpoints(), [checkpoint])

    def test_record_uses_empty_metadata_by_default(self):
        session = SessionState(session_id="session-1")
        recorder = CheckpointRecorder(session)

        checkpoint = recorder.record()

        self.assertEqual(checkpoint.metadata, {})

    def test_record_rejects_non_dict_metadata(self):
        session = SessionState(session_id="session-1")
        recorder = CheckpointRecorder(session)

        with self.assertRaises(ValueError):
            recorder.record(metadata=["not", "dict"])

    def test_list_checkpoints_returns_copy(self):
        session = SessionState(session_id="session-1")
        recorder = CheckpointRecorder(session)
        recorder.record(metadata={"reason": "after_user_input"})

        checkpoints = recorder.list_checkpoints()
        checkpoints.clear()

        self.assertEqual(len(recorder.list_checkpoints()), 1)

    def test_init_rejects_non_session_state(self):
        with self.assertRaises(TypeError):
            CheckpointRecorder(session_state={"session_id": "session-1"})


if __name__ == "__main__":
    unittest.main()
