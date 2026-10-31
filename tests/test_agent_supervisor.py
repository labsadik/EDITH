"""End-to-end LangGraph supervisor workflow tests with deterministic Powerful Brain replies."""
import json
import unittest
from unittest.mock import patch

from core import agent_supervisor
from memory import rag_store


class AgentSupervisorWorkflowTests(unittest.TestCase):
    def test_retrieve_plan_delegate_and_synthesize_run_in_graph_order(self):
        replies = [
            json.dumps({"tasks": [
                {"role": "researcher", "task": "Find the relevant facts"},
                {"role": "security", "task": "Check trust boundaries"},
            ]}),
            "Research found the supported behavior.",
            "Security found no unsafe write path.",
            "The result is grounded and safe.",
        ]
        with (
            patch.object(rag_store, "search_knowledge", return_value=[
                {"source": "fixture.md", "text": "Trusted local note", "score": 0.1},
            ]) as retrieve,
            patch.object(agent_supervisor, "call_brain_text", side_effect=replies) as brain,
        ):
            answer = agent_supervisor.run_agent_supervisor("Review the local project")
        self.assertEqual(answer, "The result is grounded and safe.")
        retrieve.assert_called_once_with("Review the local project", limit=5)
        self.assertEqual(brain.call_count, 4)
        self.assertIn("Trusted local note", brain.call_args_list[0].args[0])
        self.assertEqual(
            brain.call_args_list[1].kwargs["system"],
            agent_supervisor._SPECIALISTS["researcher"],
        )
        self.assertEqual(
            brain.call_args_list[2].kwargs["system"],
            agent_supervisor._SPECIALISTS["security"],
        )

    def test_invalid_plan_falls_back_to_a_bounded_planner_task(self):
        with (
            patch.object(rag_store, "search_knowledge", return_value=[]),
            patch.object(agent_supervisor, "call_brain_text", side_effect=[
                "not JSON", "A bounded fallback plan", "A final answer",
            ]) as brain,
        ):
            answer = agent_supervisor.run_agent_supervisor("Explain the app architecture")
        self.assertEqual(answer, "A final answer")
        self.assertEqual(brain.call_count, 3)
        self.assertIn("Explain the app architecture", brain.call_args_list[1].args[0])

    def test_empty_request_is_rejected_before_graph_execution(self):
        with self.assertRaises(ValueError):
            agent_supervisor.run_agent_supervisor("   ")

    def test_provider_http_429_returns_a_structured_failure_without_claiming_completion(self):
        class RateLimitedProviderError(RuntimeError):
            status_code = 429

        class FailedGraph:
            def invoke(self, _state):
                raise RateLimitedProviderError("Too Many Requests")

        with patch.object(agent_supervisor, "_build_graph", return_value=FailedGraph()):
            result = agent_supervisor.run_agent_supervisor("Build a report")

        self.assertIn("Agent Supervisor failed", result)
        self.assertIn("HTTP 429", result)
        self.assertIn("No final plan or delegated result was produced", result)

    def test_rate_limit_exception_is_detected_through_cause_chain(self):
        provider_error = RuntimeError("429 Client Error: Too Many Requests")
        wrapper_error = RuntimeError("LLM call failed")
        wrapper_error.__cause__ = provider_error
        self.assertTrue(agent_supervisor._is_rate_limit_error(wrapper_error))


if __name__ == "__main__":
    unittest.main()
