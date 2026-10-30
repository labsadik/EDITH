"""Provider probe and runtime response parsing regression tests."""
import unittest
from unittest.mock import Mock, patch

from core import llm_client
from core import provider_registry as providers


def _response(payload, status=200):
    response = Mock()
    response.status_code = status
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    response.content = b"{}"
    return response


class ProviderRegressionTests(unittest.TestCase):
    def test_voice_probe_allows_selected_gender_preset(self):
        import inspect
        self.assertIn("voice_name", inspect.signature(providers.probe_voice_provider).parameters)

    def test_ollama_probe_disables_thinking_and_reads_final_content(self):
        response = _response({"message": {"thinking": "private reasoning", "content": "OK"}})
        with patch.object(providers.requests, "post", return_value=response) as post:
            result = providers.probe_provider("ollama", "http://localhost:11434", "qwen3")
        self.assertTrue(result["ok"])
        payload = post.call_args.kwargs["json"]
        self.assertFalse(payload["think"])
        self.assertGreaterEqual(payload["options"]["num_predict"], 32)

    def test_openai_probe_accepts_text_content_blocks(self):
        response = _response({"choices": [{"message": {"content": [
            {"type": "text", "text": "O"}, {"type": "text", "text": "K"}
        ]}}]})
        with patch.object(providers.requests, "post", return_value=response):
            result = providers.probe_provider("openai", "https://api.openai.com/v1", "gpt-test", "secret")
        self.assertTrue(result["ok"])

    def test_anthropic_probe_uses_sufficient_budget_and_block_parser(self):
        response = _response({"content": [{"type": "text", "text": "OK"}]})
        with patch.object(providers.requests, "post", return_value=response) as post:
            result = providers.probe_provider("anthropic", "https://api.anthropic.com/v1", "claude-test", "secret")
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(post.call_args.kwargs["json"]["max_tokens"], 32)
        self.assertEqual(post.call_args.args[0], "https://api.anthropic.com/v1/messages")

    def test_runtime_ollama_uses_non_thinking_final_response(self):
        response = _response({"message": {"content": "runtime OK", "tool_calls": []}})
        with (
            patch.object(llm_client, "get_llm_provider", return_value="ollama"),
            patch.object(llm_client, "get_llm_settings", return_value=("http://localhost:11434", "qwen3")),
            patch.object(llm_client.requests, "post", return_value=response) as post,
        ):
            result = llm_client.call_llm([{"role": "user", "content": "hello"}])
        self.assertEqual(result["content"], "runtime OK")
        self.assertFalse(post.call_args.kwargs["json"]["think"])

    def test_runtime_anthropic_normalizes_text_blocks(self):
        response = _response({"content": [
            {"type": "text", "text": "hello "}, {"type": "text", "text": "world"}
        ]})
        with (
            patch.object(llm_client, "get_llm_provider", return_value="anthropic"),
            patch.object(llm_client, "get_llm_settings", return_value=("https://api.anthropic.com/v1", "claude-test")),
            patch.object(llm_client, "_cloud_headers", return_value={"x-api-key": "secret"}),
            patch.object(llm_client.requests, "post", return_value=response),
        ):
            result = llm_client.call_llm([{"role": "user", "content": "hello"}])
        self.assertEqual(result["content"], "hello world")

    def test_ollama_probe_retries_without_think_for_older_servers(self):
        old_api = _response({}, status=400)
        final = _response({"message": {"content": "OK"}})
        with patch.object(providers.requests, "post", side_effect=[old_api, final]) as post:
            result = providers.probe_provider("ollama", "http://localhost:11434", "llama3")
        self.assertTrue(result["ok"])
        self.assertIs(post.call_args_list[0].kwargs["json"].get("think"), False)
        self.assertNotIn("think", post.call_args_list[1].kwargs["json"])

    def test_anthropic_runtime_maps_tool_use_blocks_to_edith_tool_calls(self):
        response = _response({"content": [{
            "type": "tool_use", "id": "toolu_123", "name": "lookup_weather",
            "input": {"city": "Kolkata"},
        }]})
        tools = [{
            "type": "function",
            "function": {
                "name": "lookup_weather",
                "description": "Look up local weather",
                "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
            },
        }]
        with (
            patch.object(llm_client, "get_llm_provider", return_value="anthropic"),
            patch.object(llm_client, "get_llm_settings", return_value=("https://api.anthropic.com/v1", "claude-test")),
            patch.object(llm_client, "_cloud_headers", return_value={"x-api-key": "secret"}),
            patch.object(llm_client.requests, "post", return_value=response) as post,
        ):
            result = llm_client.call_llm(
                [{"role": "user", "content": "Weather in Kolkata?"}], tools=tools
            )
        self.assertEqual(result["tool_calls"][0]["id"], "toolu_123")
        self.assertEqual(result["tool_calls"][0]["function"]["arguments"], {"city": "Kolkata"})
        self.assertEqual(post.call_args.kwargs["json"]["tools"][0]["input_schema"]["type"], "object")


if __name__ == "__main__":
    unittest.main()
