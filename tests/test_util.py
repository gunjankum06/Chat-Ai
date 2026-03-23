import unittest

from agent.util import safe_parse_llm_json, validate_decision


class TestUtil(unittest.TestCase):
    def test_safe_parse_llm_json_valid(self):
        obj = safe_parse_llm_json('{"type":"final","content":"ok"}')
        self.assertEqual(obj["type"], "final")
        self.assertEqual(obj["content"], "ok")

    def test_validate_decision_final(self):
        decision = validate_decision({"type": "final", "content": "done"})
        self.assertEqual(decision.type, "final")
        self.assertEqual(decision.content, "done")

    def test_validate_decision_tool_call(self):
        decision = validate_decision({
            "type": "tool_call",
            "name": "greet",
            "arguments": {"name": "Ada"},
        })
        self.assertEqual(decision.type, "tool_call")
        self.assertEqual(decision.name, "greet")
        self.assertEqual(decision.arguments, {"name": "Ada"})


if __name__ == "__main__":
    unittest.main()
