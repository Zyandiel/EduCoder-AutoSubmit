import io
import http.client
import json
import unittest
import urllib.error
import urllib.request
from dataclasses import replace
from unittest.mock import MagicMock, patch

from ai.client import (AIError, AiOptions, DeepSeekClient, ENDPOINT, MAX_RESPONSE_BYTES,
                       _NoRedirect, prepare_problem, validate_solution)


def problem():
    return {"assignment": "C++ 示例", "title": "加法", "description": "读取两个整数，输出其和。",
            "files": [{"path": "step1/main.cpp", "code": "// TODO", "editable": True},
                      {"path": "step1/README.txt", "code": "只读", "editable": False}]}


def solution():
    return {"status": "ready", "reason": "完成加法", "files": [
        {"path": "step1/main.cpp", "code": "int main(){return 0;}\n"}]}


def response_body(value=None, *, finish="stop"):
    return json.dumps({"choices": [{"finish_reason": finish, "message": {
        "content": json.dumps(solution() if value is None else value, ensure_ascii=False)}}],
        "usage": {"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168}}, ensure_ascii=False).encode()


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.client = DeepSeekClient(AiOptions(), "sk-unit-test-placeholder")

    def response(self, raw):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = io.BytesIO(raw)
        return patch("ai.client.urllib.request.build_opener", return_value=opener), opener

    def test_structured_request_excludes_page_and_session_data(self):
        case = problem()
        case.update(url="https://example.invalid/?token=private", cookies="private-cookie", html="private-html")
        case["files"][0]["secret"] = "not-a-template-field"
        mocked, opener = self.response(response_body())
        with mocked, self.assertLogs(level="INFO") as logs:
            result = self.client.solve(case)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, ENDPOINT)
        self.assertEqual(request.get_header("Authorization"), "Bearer sk-unit-test-placeholder")
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 180)
        sent = json.loads(request.data)
        content = json.loads(sent["messages"][1]["content"])
        self.assertEqual(set(content), {"assignment", "title", "description", "files"})
        self.assertEqual(content["files"][0], problem()["files"][0])
        self.assertNotIn("private", request.data.decode())
        self.assertEqual(sent["response_format"], {"type": "json_object"})
        self.assertFalse(sent["stream"])
        self.assertEqual(result["files"], solution()["files"])
        self.assertEqual(result["usage"]["total_tokens"], 168)
        self.assertNotIn("sk-unit-test-placeholder", "\n".join(logs.output))
        self.assertEqual(self.client.calls, 1)

    def test_missing_information_is_explicit_not_guessed(self):
        value = {"status": "needs_context", "reason": "缺少书上的公式", "files": []}
        mocked, _ = self.response(response_body(value))
        with mocked:
            self.assertEqual(self.client.solve(problem())["status"], "needs_context")

    def test_input_invalid_or_oversized_never_requests(self):
        cases = []
        empty = problem(); empty["description"] = ""; cases.append(empty)
        bad_path = problem(); bad_path["files"][0]["path"] = "../escape.cpp"; cases.append(bad_path)
        read_only = problem(); read_only["files"][0]["editable"] = False; cases.append(read_only)
        too_big = problem(); too_big["description"] = "x" * 160001; cases.append(too_big)
        duplicate = problem(); duplicate["files"].append(duplicate["files"][0]); cases.append(duplicate)
        with patch("ai.client.urllib.request.build_opener") as build:
            for case in cases:
                with self.subTest(case=case["title"]), self.assertRaises(AIError):
                    self.client.solve(case)
            build.assert_not_called()
        self.assertEqual(self.client.calls, 0)

    def test_only_known_editable_unique_paths_are_allowed(self):
        paths = ["../../escape.cpp", "C:/escape.cpp", "/tmp/escape.cpp", "step1\\main.cpp",
                 "step1/new.cpp", "step1/README.txt", "step1//main.cpp", "step1/./main.cpp"]
        for path in paths:
            value = solution(); value["files"][0]["path"] = path
            with self.subTest(path=path), self.assertRaises(AIError):
                validate_solution(value, problem())
        value = solution(); value["files"].append(dict(value["files"][0]))
        with self.assertRaises(AIError):
            validate_solution(value, problem())

    def test_rejects_ambiguous_or_empty_solution(self):
        cases = [None, {}, {**solution(), "extra": "unexpected"}, {**solution(), "status": "done"},
                 {**solution(), "files": []}, {"status": "needs_context", "reason": "", "files": []},
                 {**solution(), "status": "needs_context"}]
        for code in ("", "  ", "```cpp\nhello\n```", "hello\x00world", None):
            value = solution(); value["files"][0]["code"] = code; cases.append(value)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(AIError):
                validate_solution(value, problem())

    def test_incomplete_output_is_never_accepted(self):
        for finish in ("length", "tool_calls", "content_filter", None):
            mocked, _ = self.response(response_body(finish=finish))
            with mocked, self.subTest(finish=finish), self.assertRaisesRegex(AIError, "未完整结束"):
                self.client.solve(problem())

    def test_bad_json_and_empty_output(self):
        cases = [b"not json", b"{}", b"null", b"[]", b'\xff',
                 b'{"choices": [{"finish_reason":"stop","message":{"content":"   "}}]}',
                 b'{"choices": [{"finish_reason":"stop","message":{"content":"not-json"}}]}']
        for raw in cases:
            mocked, _ = self.response(raw)
            with mocked, self.subTest(raw=raw), self.assertRaises(AIError) as error:
                self.client.solve(problem())
            self.assertFalse(error.exception.fatal_run)

    def test_response_bound(self):
        mocked, _ = self.response(b" " * (MAX_RESPONSE_BYTES + 1))
        with mocked, self.assertRaisesRegex(AIError, "大小限制"):
            self.client.solve(problem())

    def test_http_error_is_redacted_and_not_retried(self):
        for code in (302, 400, 401, 402, 403, 429, 500, 503):
            remote = io.BytesIO(b"secret-body sk-unit-test-placeholder")
            error = urllib.error.HTTPError(ENDPOINT, code, "secret-message", {}, remote)
            with patch("ai.client.urllib.request.build_opener") as build:
                build.return_value.open.side_effect = error
                with self.subTest(code=code), self.assertRaises(AIError) as caught:
                    self.client.solve(problem())
                build.return_value.open.assert_called_once()
            self.assertTrue(caught.exception.fatal_run)
            self.assertNotIn("secret", str(caught.exception))
            self.assertNotIn("sk-unit", str(caught.exception))
            self.assertTrue(remote.closed)

    def test_network_and_timeout_stop_run_without_retry(self):
        for error in (TimeoutError("secret-timeout"), urllib.error.URLError("secret-host"),
                      http.client.IncompleteRead(b"secret-partial-response")):
            with patch("ai.client.urllib.request.build_opener") as build:
                build.return_value.open.side_effect = error
                with self.assertRaises(AIError) as caught:
                    self.client.solve(problem())
                build.return_value.open.assert_called_once()
                self.assertTrue(caught.exception.fatal_run)
                self.assertNotIn("secret", str(caught.exception))

    def test_duplicate_json_keys_and_nonstandard_numbers_rejected(self):
        output = '{"status":"needs_context","status":"ready","reason":"x","files":[]}'
        cases = [b'{"choices":[],"choices":[]}', b'{"choices":[],"usage":NaN}',
                 json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": output}}]}).encode()]
        for raw in cases:
            mocked, _ = self.response(raw)
            with mocked, self.subTest(raw=raw), self.assertRaises(AIError):
                self.client.solve(problem())

    def test_budget_counts_requests_and_stops_before_next(self):
        client = DeepSeekClient(replace(AiOptions(), max_calls_per_run=1), "sk-fake-test-key")
        mocked, opener = self.response(response_body())
        with mocked:
            client.solve(problem())
            with self.assertRaisesRegex(AIError, "max_calls_per_run") as error:
                client.solve(problem())
        self.assertTrue(error.exception.fatal_run)
        opener.open.assert_called_once()

    def test_redirect_handler_cannot_forward_authorization(self):
        request = urllib.request.Request(ENDPOINT, headers={"Authorization": "Bearer fake"})
        self.assertIsNone(_NoRedirect().redirect_request(request, None, 302, "", {}, "https://other.invalid"))

    def test_configuration_bounds(self):
        invalid = ({"enabled": "true"}, {"model": "invalid\nheader"}, {"timeout_seconds": 0},
                   {"max_tokens": -1}, {"max_calls_per_run": True}, {"max_context_chars": 999})
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                AiOptions(**kwargs)
        self.assertEqual(AiOptions().max_calls_per_run, 100)


if __name__ == "__main__":
    unittest.main()
