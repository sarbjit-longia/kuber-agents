from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.backtesting.runtime_launcher import DockerContainerBacktestLauncher, KubernetesJobBacktestLauncher
from app.config import settings


@pytest.mark.no_tool_mocks
def test_kubernetes_launcher_builds_job_spec_with_runtime_contract(monkeypatch):
    launcher = KubernetesJobBacktestLauncher.__new__(KubernetesJobBacktestLauncher)
    launcher._config_source = "kubeconfig"

    monkeypatch.setattr(settings, "BACKTEST_RUNTIME_IMAGE", "ghcr.io/acme/backtest-runtime:latest")
    monkeypatch.setattr(settings, "BACKTEST_RUNTIME_NAMESPACE", "backtest")
    monkeypatch.setattr(settings, "BACKTEST_RUNTIME_K8S_NAMESPACE", "backtest-jobs")
    monkeypatch.setattr(settings, "BACKTEST_RUNTIME_K8S_SERVICE_ACCOUNT", "backtest-runtime")
    monkeypatch.setattr(settings, "BACKTEST_RUNTIME_K8S_IMAGE_PULL_POLICY", "Always")
    monkeypatch.setattr(settings, "BACKTEST_RUNTIME_K8S_IMAGE_PULL_SECRETS", ["registry-creds"])
    monkeypatch.setattr(settings, "BACKTEST_RUNTIME_K8S_JOB_TTL_SECONDS", 7200)
    monkeypatch.setattr(settings, "BACKTEST_RUNTIME_K8S_ACTIVE_DEADLINE_SECONDS", 1800)
    monkeypatch.setattr(
        settings,
        "BACKTEST_RUNTIME_ENV_PASSTHROUGH",
        ["DATABASE_URL", "REDIS_URL"],
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("REDIS_URL", "redis://example")

    job = launcher._build_job("11111111-2222-3333-4444-555555555555")

    assert job.metadata.name == "backtest-111111112222"
    assert job.metadata.labels["clovercharts.runtime"] == "backtest"
    assert job.spec.ttl_seconds_after_finished == 7200
    assert job.spec.active_deadline_seconds == 1800

    pod_spec = job.spec.template.spec
    assert pod_spec.restart_policy == "Never"
    assert pod_spec.service_account_name == "backtest-runtime"
    assert [secret.name for secret in pod_spec.image_pull_secrets] == ["registry-creds"]

    container = pod_spec.containers[0]
    assert container.name == "backtest-runtime"
    assert container.image == "ghcr.io/acme/backtest-runtime:latest"
    assert container.image_pull_policy == "Always"
    assert container.command == ["python", "-m", "app.backtesting.runtime_main"]

    env = {item.name: item.value for item in container.env}
    assert env["BACKTEST_RUN_ID"] == "11111111-2222-3333-4444-555555555555"
    assert env["BACKTEST_RUNTIME_MODE"] == "kubernetes_job"
    assert env["BACKTEST_RUNTIME_NAMESPACE"] == "backtest"
    assert env["DATABASE_URL"] == "postgresql://example"
    assert env["REDIS_URL"] == "redis://example"


@pytest.mark.no_tool_mocks
def test_kubernetes_launcher_stop_deletes_job(monkeypatch):
    launcher = KubernetesJobBacktestLauncher.__new__(KubernetesJobBacktestLauncher)
    calls = []

    launcher.batch_api = SimpleNamespace(
        delete_namespaced_job=lambda **kwargs: calls.append(kwargs)
    )
    monkeypatch.setattr(settings, "BACKTEST_RUNTIME_K8S_NAMESPACE", "backtest-jobs")
    monkeypatch.setattr(settings, "BACKTEST_RUNTIME_NAMESPACE", "backtest")

    stopped = launcher.stop({"job_name": "backtest-123", "namespace": "backtest-jobs"})

    assert stopped is True
    assert calls == [
        {
            "name": "backtest-123",
            "namespace": "backtest-jobs",
            "propagation_policy": "Background",
        }
    ]


@pytest.mark.no_tool_mocks
def test_docker_launcher_autodetects_current_compose_network(monkeypatch):
    launcher = DockerContainerBacktestLauncher.__new__(DockerContainerBacktestLauncher)
    launcher.client = SimpleNamespace(
        containers=SimpleNamespace(
            get=lambda _container_id: SimpleNamespace(
                attrs={
                    "NetworkSettings": {
                        "Networks": {
                            "kuber-agents_default": {},
                        }
                    }
                }
            )
        )
    )

    monkeypatch.setattr(settings, "BACKTEST_RUNTIME_DOCKER_NETWORK", None)
    monkeypatch.setenv("HOSTNAME", "worker-container-id")

    assert launcher._resolve_network() == "kuber-agents_default"


@pytest.mark.no_tool_mocks
def test_docker_launcher_maps_backtest_kafka_env_for_embedded_signal_generator(monkeypatch):
    launcher = DockerContainerBacktestLauncher.__new__(DockerContainerBacktestLauncher)
    monkeypatch.setattr(
        settings,
        "BACKTEST_RUNTIME_ENV_PASSTHROUGH",
        ["BACKTEST_KAFKA_BOOTSTRAP_SERVERS", "BACKTEST_KAFKA_SIGNAL_TOPIC"],
    )
    monkeypatch.setattr(settings, "BACKTEST_RUNTIME_NAMESPACE", "backtest")
    monkeypatch.setenv("BACKTEST_KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    monkeypatch.setenv("BACKTEST_KAFKA_SIGNAL_TOPIC", "trading-signals-backtest")

    env = launcher._build_environment("11111111-2222-3333-4444-555555555555")

    assert env["BACKTEST_KAFKA_BOOTSTRAP_SERVERS"] == "kafka:9092"
    assert env["BACKTEST_KAFKA_SIGNAL_TOPIC"] == "trading-signals-backtest"
    assert env["KAFKA_BOOTSTRAP_SERVERS"] == "kafka:9092"
    assert env["KAFKA_SIGNAL_TOPIC"] == "trading-signals-backtest"


@pytest.mark.no_tool_mocks
def test_kubernetes_launcher_maps_backtest_kafka_env_for_embedded_signal_generator(monkeypatch):
    launcher = KubernetesJobBacktestLauncher.__new__(KubernetesJobBacktestLauncher)
    monkeypatch.setattr(
        settings,
        "BACKTEST_RUNTIME_ENV_PASSTHROUGH",
        ["BACKTEST_KAFKA_BOOTSTRAP_SERVERS", "BACKTEST_KAFKA_SIGNAL_TOPIC"],
    )
    monkeypatch.setattr(settings, "BACKTEST_RUNTIME_NAMESPACE", "backtest")
    monkeypatch.setenv("BACKTEST_KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    monkeypatch.setenv("BACKTEST_KAFKA_SIGNAL_TOPIC", "trading-signals-backtest")

    env = launcher._build_environment("11111111-2222-3333-4444-555555555555")
    env_map = {item.name: item.value for item in env}

    assert env_map["BACKTEST_KAFKA_BOOTSTRAP_SERVERS"] == "kafka:9092"
    assert env_map["BACKTEST_KAFKA_SIGNAL_TOPIC"] == "trading-signals-backtest"
    assert env_map["KAFKA_BOOTSTRAP_SERVERS"] == "kafka:9092"
    assert env_map["KAFKA_SIGNAL_TOPIC"] == "trading-signals-backtest"
