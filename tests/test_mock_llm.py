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

    async def test_reads_last_user_not_tool(self):
        llm = MockLLM()
        messages = [
            {"role": "user", "content": "get defect 1234 details"},
            {"role": "tool", "name": "get_defect_details", "content": "{}"},
        ]
        raw = await llm.complete(messages)
        obj = json.loads(raw)
        self.assertEqual(obj["type"], "tool_call")
        self.assertEqual(obj["name"], "get_defect_details")
        self.assertEqual(obj["arguments"], {"defectId": "1234"})


if __name__ == "__main__":
    unittest.main()
