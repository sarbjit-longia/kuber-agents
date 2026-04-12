# Backtest Runtime Kubernetes Manifests

These manifests support the per-run `kubernetes_job` backtest launcher.

They do **not** create a static Deployment for backtests. The backend launcher
creates one Job per `BacktestRun`.

## What this directory provides

- `namespace.yaml`
  - dedicated namespace for backtest runtimes
- `serviceaccounts.yaml`
  - `backtest-runtime`: service account used by ephemeral backtest runtime pods
- `backend-job-manager-rbac.yaml`
  - Role and RoleBinding template allowing the backend worker to manage Jobs in the backtest namespace
- `kustomization.yaml`
  - convenience entrypoint for `kubectl apply -k`

## Recommended setup

1. Apply these manifests:

```bash
kubectl apply -k deploy/kubernetes/backtest-runtime
```

2. Configure the backend worker environment:

```bash
BACKTEST_RUNTIME_MODE=kubernetes_job
BACKTEST_RUNTIME_IMAGE=ghcr.io/your-org/kuber-agents-backend:<tag>
BACKTEST_RUNTIME_K8S_NAMESPACE=backtest
BACKTEST_RUNTIME_K8S_SERVICE_ACCOUNT=backtest-runtime
```

3. Update `deploy/kubernetes/backtest-runtime/backend-job-manager-rbac.yaml` so the
   `subjects` entry points at the service account and namespace used by your backend worker.

## Notes

- The runtime image should be the backend image that already contains:
  - backend code
  - signal-generator Python dependencies
  - embedded signal-generator source under `/opt/signal-generator`
- The runtime pod does not need Kubernetes API permissions by default.
- The backend worker usually runs outside the `backtest` namespace. Adjust the
  `RoleBinding.subjects[0]` service account reference before applying.
- Backtest isolation still depends on application-level scoping:
  - `backtest_run_id`
  - `mode=backtest`
  - namespaced Redis keys
  - backtest-only Kafka topics if enabled
