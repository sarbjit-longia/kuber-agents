"""
Backtest runtime launcher abstraction.

Phase 1 keeps the legacy shared-runtime path available as a bridge while the
ephemeral per-run container launcher is implemented in later phases.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Dict, Optional

import structlog
try:
    import docker
    from docker.errors import DockerException
except ImportError:  # pragma: no cover - optional until docker mode is used
    docker = None

    class DockerException(Exception):
        pass
try:
    from kubernetes import client as k8s_client
    from kubernetes import config as k8s_config
    from kubernetes.client.exceptions import ApiException
except ImportError:  # pragma: no cover - optional until kubernetes mode is used
    k8s_client = None
    k8s_config = None
    ApiException = Exception

from app.config import settings

logger = structlog.get_logger()


@dataclass
class BacktestLaunchResult:
    launcher_mode: str
    accepted: bool
    details: Optional[Dict] = None


class BacktestRuntimeLauncher:
    def launch(self, backtest_run_id: str) -> BacktestLaunchResult:
        raise NotImplementedError

    def stop(self, runtime_details: Optional[Dict]) -> bool:
        return False


class LegacySharedBacktestLauncher(BacktestRuntimeLauncher):
    """
    Temporary bridge to the existing shared-runtime backtest execution path.

    This is not the target architecture. It exists so Phase 1 can move the
    control plane to a launcher contract before Phase 2 introduces an actual
    ephemeral runtime backend.
    """

    def launch(self, backtest_run_id: str) -> BacktestLaunchResult:
        from app.orchestration.tasks.run_backtest import run_backtest

        run_backtest.apply_async(
            kwargs={"backtest_run_id": backtest_run_id},
            queue="backtest_pipeline_execution",
            expires=60 * 60 * 6,
        )
        logger.info(
            "backtest_runtime_launch_delegated_to_legacy_shared_path",
            backtest_run_id=backtest_run_id,
        )
        return BacktestLaunchResult(
            launcher_mode="legacy_shared",
            accepted=True,
            details={"queue": "backtest_pipeline_execution"},
        )


class UnsupportedEphemeralRuntimeLauncher(BacktestRuntimeLauncher):
    def __init__(self, launcher_mode: str):
        self.launcher_mode = launcher_mode

    def launch(self, backtest_run_id: str) -> BacktestLaunchResult:
        raise NotImplementedError(
            f"Backtest launcher mode '{self.launcher_mode}' is not implemented yet"
        )


class DockerContainerBacktestLauncher(BacktestRuntimeLauncher):
    def __init__(self):
        if docker is None:
            raise ImportError("docker package is required for docker_container launcher mode")
        self.client = docker.from_env()

    @staticmethod
    def _container_name(backtest_run_id: str) -> str:
        short_id = backtest_run_id.replace("-", "")[:12]
        return f"clovercharts-backtest-{short_id}"

    @staticmethod
    def _labels(backtest_run_id: str) -> Dict[str, str]:
        return {
            "clovercharts.runtime": "backtest",
            "clovercharts.backtest_run_id": backtest_run_id,
        }

    def _build_environment(self, backtest_run_id: str) -> Dict[str, str]:
        env = {
            "BACKTEST_RUN_ID": backtest_run_id,
            "BACKTEST_RUNTIME_MODE": "ephemeral_container",
            "BACKTEST_RUNTIME_NAMESPACE": settings.BACKTEST_RUNTIME_NAMESPACE,
            "PYTHONUNBUFFERED": "1",
        }
        for key in settings.BACKTEST_RUNTIME_ENV_PASSTHROUGH:
            value = os.getenv(key)
            if value is not None:
                env[key] = value
        backtest_kafka_bootstrap = env.get("BACKTEST_KAFKA_BOOTSTRAP_SERVERS")
        if backtest_kafka_bootstrap and "KAFKA_BOOTSTRAP_SERVERS" not in env:
            env["KAFKA_BOOTSTRAP_SERVERS"] = backtest_kafka_bootstrap

        backtest_kafka_topic = env.get("BACKTEST_KAFKA_SIGNAL_TOPIC")
        if backtest_kafka_topic and "KAFKA_SIGNAL_TOPIC" not in env:
            env["KAFKA_SIGNAL_TOPIC"] = backtest_kafka_topic
        return env

    def _resolve_network(self) -> Optional[str]:
        if settings.BACKTEST_RUNTIME_DOCKER_NETWORK:
            return settings.BACKTEST_RUNTIME_DOCKER_NETWORK

        current_container_id = os.getenv("HOSTNAME")
        if not current_container_id:
            return None

        try:
            current_container = self.client.containers.get(current_container_id)
            networks = (
                current_container.attrs.get("NetworkSettings", {}).get("Networks", {}) or {}
            )
            if not networks:
                return None
            return next(iter(networks.keys()))
        except DockerException as exc:
            logger.warning(
                "backtest_runtime_network_autodetect_failed",
                current_container_id=current_container_id,
                error=str(exc),
            )
            return None

    def launch(self, backtest_run_id: str) -> BacktestLaunchResult:
        if not settings.BACKTEST_RUNTIME_IMAGE:
            raise ValueError("BACKTEST_RUNTIME_IMAGE must be set for docker_container launcher mode")

        network = self._resolve_network()
        run_kwargs = dict(
            image=settings.BACKTEST_RUNTIME_IMAGE,
            command=["python", "-m", "app.backtesting.runtime_main"],
            detach=True,
            name=self._container_name(backtest_run_id),
            environment=self._build_environment(backtest_run_id),
            labels=self._labels(backtest_run_id),
            auto_remove=False,
        )
        if network:
            run_kwargs["network"] = network

        container = self.client.containers.run(
            **run_kwargs,
        )
        logger.info(
            "backtest_runtime_container_started",
            backtest_run_id=backtest_run_id,
            container_id=container.id,
            image=settings.BACKTEST_RUNTIME_IMAGE,
            network=network,
        )
        return BacktestLaunchResult(
            launcher_mode="docker_container",
            accepted=True,
            details={
                "container_id": container.id,
                "container_name": self._container_name(backtest_run_id),
                "image": settings.BACKTEST_RUNTIME_IMAGE,
                "network": network,
                "log_locator": f"docker logs {self._container_name(backtest_run_id)}",
            },
        )

    def stop(self, runtime_details: Optional[Dict]) -> bool:
        if not runtime_details:
            return False

        container_id = runtime_details.get("container_id")
        container_name = runtime_details.get("container_name")
        target = container_id or container_name
        if not target:
            return False

        try:
            container = self.client.containers.get(target)
            container.stop(timeout=10)
            logger.info(
                "backtest_runtime_container_stopped",
                container_id=container.id,
                container_name=container.name,
            )
            return True
        except DockerException as exc:
            logger.warning(
                "backtest_runtime_container_stop_failed",
                target=target,
                error=str(exc),
            )
            return False


class KubernetesJobBacktestLauncher(BacktestRuntimeLauncher):
    def __init__(self):
        if k8s_client is None or k8s_config is None:
            raise ImportError("kubernetes package is required for kubernetes_job launcher mode")

        try:
            k8s_config.load_incluster_config()
            self._config_source = "incluster"
        except Exception:
            k8s_config.load_kube_config()
            self._config_source = "kubeconfig"
        self.batch_api = k8s_client.BatchV1Api()

    @staticmethod
    def _job_name(backtest_run_id: str) -> str:
        short_id = backtest_run_id.replace("-", "")[:12]
        return f"backtest-{short_id}"

    @staticmethod
    def _labels(backtest_run_id: str) -> Dict[str, str]:
        return {
            "app.kubernetes.io/name": "clovercharts-backtest",
            "app.kubernetes.io/component": "backtest-runtime",
            "clovercharts.runtime": "backtest",
            "clovercharts.backtest_run_id": backtest_run_id,
        }

    def _namespace(self) -> str:
        return settings.BACKTEST_RUNTIME_K8S_NAMESPACE or settings.BACKTEST_RUNTIME_NAMESPACE or "default"

    def _build_environment(self, backtest_run_id: str):
        env = [
            k8s_client.V1EnvVar(name="BACKTEST_RUN_ID", value=backtest_run_id),
            k8s_client.V1EnvVar(name="BACKTEST_RUNTIME_MODE", value="kubernetes_job"),
            k8s_client.V1EnvVar(name="BACKTEST_RUNTIME_NAMESPACE", value=settings.BACKTEST_RUNTIME_NAMESPACE),
            k8s_client.V1EnvVar(name="PYTHONUNBUFFERED", value="1"),
        ]
        for key in settings.BACKTEST_RUNTIME_ENV_PASSTHROUGH:
            value = os.getenv(key)
            if value is not None:
                env.append(k8s_client.V1EnvVar(name=key, value=value))
        backtest_kafka_bootstrap = os.getenv("BACKTEST_KAFKA_BOOTSTRAP_SERVERS")
        if backtest_kafka_bootstrap and not any(item.name == "KAFKA_BOOTSTRAP_SERVERS" for item in env):
            env.append(k8s_client.V1EnvVar(name="KAFKA_BOOTSTRAP_SERVERS", value=backtest_kafka_bootstrap))

        backtest_kafka_topic = os.getenv("BACKTEST_KAFKA_SIGNAL_TOPIC")
        if backtest_kafka_topic and not any(item.name == "KAFKA_SIGNAL_TOPIC" for item in env):
            env.append(k8s_client.V1EnvVar(name="KAFKA_SIGNAL_TOPIC", value=backtest_kafka_topic))
        return env

    def _build_job(self, backtest_run_id: str):
        job_name = self._job_name(backtest_run_id)
        labels = self._labels(backtest_run_id)

        pod_spec = k8s_client.V1PodSpec(
            restart_policy="Never",
            containers=[
                k8s_client.V1Container(
                    name="backtest-runtime",
                    image=settings.BACKTEST_RUNTIME_IMAGE,
                    image_pull_policy=settings.BACKTEST_RUNTIME_K8S_IMAGE_PULL_POLICY,
                    command=["python", "-m", "app.backtesting.runtime_main"],
                    env=self._build_environment(backtest_run_id),
                )
            ],
            service_account_name=settings.BACKTEST_RUNTIME_K8S_SERVICE_ACCOUNT,
            image_pull_secrets=[
                k8s_client.V1LocalObjectReference(name=name)
                for name in settings.BACKTEST_RUNTIME_K8S_IMAGE_PULL_SECRETS
            ] or None,
        )

        template = k8s_client.V1PodTemplateSpec(
            metadata=k8s_client.V1ObjectMeta(labels=labels),
            spec=pod_spec,
        )

        spec = k8s_client.V1JobSpec(
            template=template,
            ttl_seconds_after_finished=settings.BACKTEST_RUNTIME_K8S_JOB_TTL_SECONDS,
            active_deadline_seconds=settings.BACKTEST_RUNTIME_K8S_ACTIVE_DEADLINE_SECONDS,
            backoff_limit=0,
        )

        return k8s_client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=k8s_client.V1ObjectMeta(name=job_name, labels=labels),
            spec=spec,
        )

    def launch(self, backtest_run_id: str) -> BacktestLaunchResult:
        if not settings.BACKTEST_RUNTIME_IMAGE:
            raise ValueError("BACKTEST_RUNTIME_IMAGE must be set for kubernetes_job launcher mode")

        namespace = self._namespace()
        job_name = self._job_name(backtest_run_id)
        job = self._build_job(backtest_run_id)
        self.batch_api.create_namespaced_job(namespace=namespace, body=job)
        logger.info(
            "backtest_runtime_kubernetes_job_started",
            backtest_run_id=backtest_run_id,
            job_name=job_name,
            namespace=namespace,
            image=settings.BACKTEST_RUNTIME_IMAGE,
            config_source=self._config_source,
        )
        return BacktestLaunchResult(
            launcher_mode="kubernetes_job",
            accepted=True,
            details={
                "job_name": job_name,
                "namespace": namespace,
                "image": settings.BACKTEST_RUNTIME_IMAGE,
                "config_source": self._config_source,
                "log_locator": f"kubectl logs job/{job_name} -n {namespace}",
            },
        )

    def stop(self, runtime_details: Optional[Dict]) -> bool:
        if not runtime_details:
            return False

        job_name = runtime_details.get("job_name")
        namespace = runtime_details.get("namespace") or self._namespace()
        if not job_name:
            return False

        try:
            self.batch_api.delete_namespaced_job(
                name=job_name,
                namespace=namespace,
                propagation_policy="Background",
            )
            logger.info(
                "backtest_runtime_kubernetes_job_deleted",
                job_name=job_name,
                namespace=namespace,
            )
            return True
        except ApiException as exc:
            if getattr(exc, "status", None) == 404:
                return True
            logger.warning(
                "backtest_runtime_kubernetes_job_delete_failed",
                job_name=job_name,
                namespace=namespace,
                error=str(exc),
            )
            return False


def get_backtest_runtime_launcher() -> BacktestRuntimeLauncher:
    mode = (settings.BACKTEST_RUNTIME_MODE or "legacy_shared").strip().lower()
    if mode == "legacy_shared":
        return LegacySharedBacktestLauncher()
    if mode == "docker_container":
        try:
            return DockerContainerBacktestLauncher()
        except DockerException as exc:
            logger.error("docker_backtest_runtime_launcher_init_failed", error=str(exc))
            raise
    if mode == "kubernetes_job":
        return KubernetesJobBacktestLauncher()
    logger.warning("unknown_backtest_runtime_mode_falling_back", mode=mode)
    return LegacySharedBacktestLauncher()
