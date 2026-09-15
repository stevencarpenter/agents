"""Offline dependency regression check: uv run --project eval --locked --all-extras python eval/test_dependencies.py."""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import unittest
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch

# Prevent background telemetry and remote model-price refreshes during imports.
os.environ.update(
    MLFLOW_DISABLE_TELEMETRY="true",
    MLFLOW_DISABLE_AGENT_HINT="true",
    MLFLOW_MODEL_CATALOG_URI="",
    MLFLOW_ENABLE_ASYNC_TRACE_LOGGING="false",
    LITELLM_LOCAL_MODEL_COST_MAP="true",
    EVAL_JUDGE_MODEL="anthropic:/claude-sonnet-4-6",
)

import anthropic
import mlflow
import pandas as pd
from mlflow.genai.scorers import scorer

# Anthropic 1.x switched its public HTTP client interface from httpx to httpx2.
if int(version("anthropic").split(".")[0]) >= 1:
    import httpx2 as sdk_http
else:
    import httpx as sdk_http

import agents
import run_eval
import scorers


@scorer
def offline_quality(outputs: str) -> int:
    return 5 if outputs == "offline answer" else 1


class DependencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("network disabled")))
        self.enterContext(patch.object(socket, "create_connection", side_effect=AssertionError("network disabled")))
        self.enterContext(patch.dict(os.environ, {"MLFLOW_EXPERIMENT_ID": ""}))
        tracking_uri = mlflow.get_tracking_uri()
        self.addCleanup(mlflow.set_tracking_uri, tracking_uri)
        mlflow.set_tracking_uri(f"sqlite:///{self.tmp}/tracking.db")
        self.experiment_id = mlflow.create_experiment(
            "offline-dependencies", artifact_location=Path(self.tmp, "artifacts").as_uri()
        )
        mlflow.set_experiment(experiment_id=self.experiment_id)

    def response(self, request: sdk_http.Request) -> sdk_http.Response:
        body = json.loads(request.content)
        self.assertEqual(body["messages"][0]["role"], "user")
        self.assertTrue(body["system"])
        self.assertEqual(body["max_tokens"], 8192)
        return sdk_http.Response(200, json={
            "id": "msg_offline",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": "offline "}, {"type": "text", "text": "answer"}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 2},
        })

    def test_sdk_providers(self) -> None:
        clients = (
            (anthropic.Anthropic, {"api_key": "offline"}),
            (anthropic.AnthropicBedrock, {
                "aws_access_key": "offline", "aws_secret_key": "offline", "aws_region": "us-east-1",
            }),
            (anthropic.AnthropicVertex, {
                "access_token": "offline", "project_id": "offline-project", "region": "us-east5",
            }),
        )
        for client_type, options in clients:
            with self.subTest(provider=client_type.__name__), client_type(
                **options, http_client=sdk_http.Client(transport=sdk_http.MockTransport(self.response)),
                max_retries=0,
            ) as client, patch.object(agents, "_client", return_value=client):
                for variant in ("wired", "unwired"):
                    self.assertEqual(agents.make_predict_fn(variant)("offline task", "technical-writer"), "offline answer")

    def test_mlflow_evaluation_and_csv(self) -> None:
        registered = scorers.register_all(experiment_id=self.experiment_id)
        self.assertEqual(sum(map(len, registered.values())), 9)
        self.assertEqual(
            {judge.name for judge in mlflow.genai.scorers.list_scorers(experiment_id=self.experiment_id)},
            {judge.name for judges in registered.values() for judge in judges},
        )
        out = Path(self.tmp, "results")
        with anthropic.Anthropic(
            api_key="offline", max_retries=0,
            http_client=sdk_http.Client(transport=sdk_http.MockTransport(self.response)),
        ) as client, patch.object(agents, "_client", return_value=client), patch.object(
            run_eval, "register_all", return_value={"technical-writer": [offline_quality]}
        ), patch.object(run_eval, "_OUT", out), patch.object(sys, "argv", [
            "run_eval.py", "--domains", "technical-writer", "--limit", "1",
            "--experiment", "offline-dependencies",
        ]):
            self.assertEqual(run_eval.main(), 0)
        comparison = pd.read_csv(out / "comparison.csv")
        self.assertEqual(comparison["wired"].tolist(), [5])
        self.assertEqual(comparison["unwired"].tolist(), [5])
        self.assertEqual(comparison["delta(wired-unwired)"].tolist(), [0])
        self.assertEqual(json.loads((out / "raw_metrics.json").read_text())[0]["wired"], 5)
        self.assertFalse(mlflow.search_traces(locations=[self.experiment_id]).empty)

    def test_mlflow_anthropic_judge(self) -> None:
        import requests

        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({
            "id": "msg_judge", "type": "message", "role": "assistant",
            "model": "claude-sonnet-4-6", "stop_reason": "end_turn",
            "content": [{"type": "text", "text": '{"result": 5, "rationale": "offline"}'}],
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }).encode()
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "offline"}), patch.object(
            requests.adapters.HTTPAdapter, "send", autospec=True, return_value=response
        ) as send:
            feedback = scorers.SCORERS["technical-writer"][0](
                inputs={"task": "offline task", "agent": "technical-writer"}, outputs="offline answer"
            )
        self.assertIsNone(feedback.error)
        self.assertEqual(feedback.value, 5)
        self.assertEqual(
            [call.args[1].url for call in send.call_args_list], ["https://api.anthropic.com/v1/messages"]
        )
        request = send.call_args.args[1]
        self.assertEqual(request.url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(json.loads(request.body)["model"], "claude-sonnet-4-6")

    def test_optional_provider_dependencies(self) -> None:
        import litellm
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding, rsa
        from google.oauth2.service_account import Credentials

        response = litellm.completion(
            model="vertex_ai/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "offline task"}],
            mock_response="offline answer",
        )
        self.assertEqual(response.choices[0].message.content, "offline answer")
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        credentials = Credentials.from_service_account_info({
            "type": "service_account",
            "client_email": "offline@example.invalid",
            "token_uri": "https://oauth2.googleapis.com/token",
            "private_key": key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ).decode(),
        })
        key.public_key().verify(
            credentials.sign_bytes(b"offline task"), b"offline task", padding.PKCS1v15(), hashes.SHA256()
        )


if __name__ == "__main__":
    print({name: version(name) for name in ("anthropic", "mlflow", "litellm", "cryptography", "pandas")})
    unittest.main()
