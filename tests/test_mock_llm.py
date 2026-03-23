import json
import unittest

from llm.mock_llm import MockLLM


class TestMockLLM(unittest.IsolatedAsyncioTestCase):
    async def test_greet_tool_call(self):
        llm = MockLLM()
        messages = [{"role": "user", "content": "greet Gunjan"}]
        raw = await llm.complete(messages)
        obj = json.loads(raw)
        self.assertEqual(obj["type"], "tool_call")
        self.assertEqual(obj["name"], "greet")
        self.assertEqual(obj["arguments"], {"name": "Gunjan"})

    async def test_returns_final_after_tool_result(self):
        """When a tool result is the last message, MockLLM must return a final
        answer rather than looping back into another tool call."""
        llm = MockLLM()
        tool_content = json.dumps({"content": "Hello Gunjan! This result came from an MCP tool."})
        messages = [
            {"role": "user", "content": "greet Gunjan"},
            {"role": "tool", "name": "greet", "content": tool_content},
        ]
        raw = await llm.complete(messages)
        obj = json.loads(raw)
        self.assertEqual(obj["type"], "final")
        self.assertIn("Gunjan", obj["content"])


if __name__ == "__main__":
    unittest.main()
