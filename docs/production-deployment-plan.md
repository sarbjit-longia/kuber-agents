# Production Deployment Plan

## Objective

Deploy a small but reliable production environment for the current CloverCharts stack on AWS for roughly 10 users, while minimizing cost and operational complexity.

This plan keeps the core live-data and signal-routing systems in place:
- `signal-generator`
- `trigger-dispatcher`
- `kafka`
- `zookeeper`

This plan removes non-essential self-hosted observability systems for the first production release:
- `langfuse-*`
- `prometheus`
- `grafana`
- `flower`

The production system should focus on live trading workloads, while experiments, tracing, and deep observability stay in development.

---

## Recommended Production Shape

### Keep

- `backend`
- `celery-worker`
- `celery-beat`
- `postgres` is not needed in Docker if existing AWS RDS is reused
- `redis`
- `signal-generator`
- `trigger-dispatcher`
- `kafka`
- `zookeeper`
- `data-plane`
- `data-plane-worker`
- `data-plane-beat`
- `timescaledb` only if RDS cannot absorb time-series workload yet

### Remove From Production

- `langfuse-web`
- `langfuse-worker`
- `langfuse-postgres`
- `langfuse-clickhouse`
- `langfuse-minio`
- `langfuse-minio-init`
- `prometheus`
- `grafana`
- `flower`

### AWS-Managed Replacements

- Use `CloudWatch Logs` for backend, worker, signal-generator, trigger-dispatcher, and data-plane logs
- Use `CloudWatch Alarms` for service health, CPU, memory, queue depth, and restart detection
- Use existing `RDS PostgreSQL`
- Use `ElastiCache Redis` if Redis durability and managed ops are desired; otherwise self-host Redis on EC2 is acceptable for an early deployment

---

## Deployment Strategy

### Phase 1: Conservative First Production

Use a single EC2 host for most services, plus existing RDS.

Recommended first shape:
- 1 EC2 instance for app and supporting containers
- Existing RDS for primary relational database
- Optional EBS volumes for local persistence

Containers on the EC2 host:
- `backend`
- `celery-worker`
- `celery-beat`
- `redis`
- `signal-generator`
- `trigger-dispatcher`
- `kafka`
- `zookeeper`
- `data-plane`
- `data-plane-worker`
- `data-plane-beat`

This is the lowest-friction production deployment because it keeps the current architecture intact.

### Phase 2: Managed Service Reduction

After production stabilizes:
- consider moving `redis` to ElastiCache
- consider replacing self-hosted Kafka/Zookeeper with Amazon MSK if Kafka operations become painful
- consider separating `data-plane` if time-series load grows

Do not migrate Kafka in phase 1 just for cost reasons.

---

## Infrastructure Recommendation

### EC2-Based Deployment

Recommended initial production target:
- `m7i.2xlarge` as the conservative first host
- EBS `gp3` volume sized for logs, Docker images, Kafka state, and local service persistence

Reasoning:
- Kafka, Zookeeper, Celery, data-plane workers, and API services all consume memory even at low user count
- a smaller host may work, but `m7i.2xlarge` gives safer operational headroom for day 1

If production load stays light after removing Langfuse, Grafana, Prometheus, and Flower, re-evaluate down-sizing after observing:
- CPU usage
- memory pressure
- Kafka stability
- Celery concurrency needs
- data-plane workload

---

## Estimated Daily Cost

These estimates assume:
- AWS `us-east-1`
- existing RDS is already paid for separately
- light traffic
- one EC2 host

### Conservative v1

- EC2 `m7i.2xlarge`: about `$9.7/day`
- EBS `gp3` 200-250 GB: about `$0.5-0.7/day`
- public IPv4: about `$0.12/day`

Estimated total:
- about `$10.5-11.5/day`
- use `$12/day` as a safe conservative planning number

### After Removing Self-Hosted Observability

Most savings come from being able to run a smaller instance later, not from separate AWS line items, because Prometheus/Grafana/Langfuse were sharing the same box.

If removal allows downsizing:
- potential target could move closer to `$7-9/day`

Do not assume that immediately. Confirm with real metrics first.

---

## Why Kafka Stays For Now

Kafka remains in production for this phase because:
- `signal-generator -> kafka -> trigger-dispatcher` is part of the current core execution path
- replacing Kafka with EventBridge/SQS requires moderate refactoring
- the direct infrastructure savings are not large enough yet to justify the migration

Kafka should be revisited later only if one of these becomes true:
- Kafka operations become a reliability issue
- the team wants to reduce operational burden more than preserve current architecture
- the event contract is stabilized and can be abstracted behind a transport interface

---

## CloudWatch Plan

Use CloudWatch instead of self-hosted Grafana/Prometheus/Langfuse in production for now.

### Logs

Send stdout/stderr for:
- `backend`
- `celery-worker`
- `celery-beat`
- `signal-generator`
- `trigger-dispatcher`
- `data-plane`
- `data-plane-worker`
- `data-plane-beat`
- `kafka`

### Metrics and Alarms

Create alarms for:
- EC2 CPU high
- EC2 memory high
- disk utilization
- container restart count
- backend health endpoint failure
- Celery worker health failure
- Kafka container restart or unhealthy state
- Redis memory pressure

### Dashboards

Create one CloudWatch dashboard for:
- host health
- backend request errors
- Celery worker health
- signal-generator activity
- trigger-dispatcher activity

---

## Terraform Decision

### Short Answer

Yes, Terraform is the better long-term choice for production infrastructure.

### Why Terraform Is Better

- repeatable infrastructure creation
- version-controlled changes
- easier environment parity between staging and production
- safer changes to networking, EC2, IAM, security groups, and CloudWatch
- easier handoff to another engineer later

### Why Not Block On It

Terraform is better for infrastructure, but it should not delay the first production deployment.

Recommended approach:
- use Terraform for AWS infrastructure
- keep container runtime deployment simple at first

That means:
- Terraform manages VPC, subnet, EC2, IAM, security groups, EBS, and optionally CloudWatch resources
- Docker Compose still starts the application containers on the EC2 host

This is the best tradeoff for the current stage: low deployment friction without manually clicking through AWS.

### Recommended Split

Use Terraform for:
- VPC and networking
- EC2 instance
- security groups
- IAM roles
- EBS volumes
- Route 53 if needed
- CloudWatch log groups and alarms

Do not overcomplicate phase 1 with:
- ECS migration
- MSK migration
- service mesh
- full Kubernetes

---

## Production Rollout Plan

### Step 1

Create a production Compose variant or deployment instructions that exclude:
- `langfuse-*`
- `grafana`
- `prometheus`
- `flower`
- local `postgres` if RDS is reused

### Step 2

Provision AWS infrastructure:
- EC2 host
- security groups
- EBS
- CloudWatch logs/alarms
- DNS if needed

### Step 3

Deploy the core containers:
- backend
- celery-worker
- celery-beat
- redis
- signal-generator
- trigger-dispatcher
- kafka
- zookeeper
- data-plane
- data-plane-worker
- data-plane-beat

### Step 4

Point the application to:
- AWS RDS
- production broker credentials
- production market data credentials
- production OpenAI/OpenRouter credentials

### Step 5

Validate:
- backend health endpoint
- signal generation
- trigger dispatch
- pipeline execution
- Celery task processing
- broker connectivity

### Step 6

Observe for 1-2 weeks, then re-evaluate:
- EC2 size
- Redis placement
- TimescaleDB need
- Kafka future

---

## Future Decisions

After the first production release:
- decide whether Kafka stays self-hosted or moves to MSK
- decide whether Redis moves to ElastiCache
- decide whether TimescaleDB remains separate
- decide whether Langfuse returns as a managed or isolated observability stack

For now, the best production posture is:
- keep core execution systems
- remove observability systems that add cost and operational burden
- use CloudWatch for production visibility
- use Terraform for infrastructure, but keep application deployment simple
