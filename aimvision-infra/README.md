# aimvision-infra

Single Helm chart that deploys the entire AIMVISION stack — backend (FastAPI),
Arq workers, web (React), CloudNativePG-managed Postgres, and (federation tier
only) MinIO + Ollama. The chart runs identically on Railway-managed Kubernetes
(cloud) and on a federation k3s appliance (on-prem).

This is the architectural commitment from
[ADR-0005 — CloudNativePG + single Helm chart for cloud↔on-prem parity](../docs/adr/0005-cloudnativepg-cloud-onprem-parity.md).

> **Container images are identical in both shapes.** Differences are values,
> secrets, replica counts, and which storage class is requested. There is no
> `if cloud else on_prem` branch in any container.

---

## Layout

```
aimvision-infra/
├── helm/aimvision/
│   ├── Chart.yaml                # AIMVISION chart, v0.1.0
│   ├── values.yaml               # safe defaults
│   ├── values-cloud.yaml         # Railway-managed k8s overrides
│   ├── values-onprem.yaml        # federation k3s appliance overrides
│   ├── values-dev.yaml           # kind/k3d laptop loop
│   ├── templates/                # Deployments, Services, Ingresses, …
│   └── tests/test-connection.yaml  # `helm test` health probe
├── manifests/
│   ├── cnpg-operator/            # operator install instructions
│   ├── cert-manager/             # operator install instructions
│   └── sealed-secrets/           # operator install instructions
├── scripts/
│   ├── install-prereqs.sh        # one-shot operator install
│   ├── helm-lint.sh              # lint against every overlay
│   └── helm-template.sh          # render /tmp/aimvision-{cloud,onprem,dev}.yaml
├── Makefile
└── README.md
```

---

## Prerequisites (cluster-wide operators)

The chart **does not** vendor the operators it depends on. Install once per
cluster:

| Operator           | Purpose                                       | Cloud | On-prem |
| ------------------ | --------------------------------------------- | :---: | :-----: |
| CloudNativePG      | Postgres lifecycle (HA, backups, failover)    |  yes  |   yes   |
| cert-manager       | TLS issuance for ingresses                    |  yes  |   yes   |
| sealed-secrets     | Air-gappable secret encryption (on-prem)      |       |   yes   |
| External Secrets   | Pulls from AWS/GCP Secret Manager (cloud)     |  yes  |         |

```sh
./scripts/install-prereqs.sh cloud      # or `onprem`, or `dev`
```

Manifest-level install notes for each operator live in `manifests/<name>/`.

---

## Quickstart

```sh
# Lint the chart against every overlay (catches template typos before kubectl)
make helm-lint

# Render to /tmp for review
make helm-template-cloud
make helm-template-onprem
make helm-template-dev

# Install
make install-prereqs-onprem
make install-onprem

# Smoke-test once Pods are Ready
make test
```

---

## Per-environment install

### Cloud (Railway-managed Kubernetes)

```sh
./scripts/install-prereqs.sh cloud
helm upgrade --install aim-cloud helm/aimvision \
  -f helm/aimvision/values.yaml \
  -f helm/aimvision/values-cloud.yaml \
  --namespace aimvision --create-namespace \
  --wait --timeout=10m
```

What it gives you:
- 3-replica backend with HPA (3–20)
- 4-replica Arq workers
- 3-instance CloudNativePG cluster, gp3 SSD, S3 backups (30-day retention)
- ExternalSecrets pulling from AWS Secrets Manager via `ClusterSecretStore`
- No MinIO, no Ollama (cloud uses S3 + Anthropic)
- ServiceMonitor disabled — Grafana Cloud agent scrapes via cluster-wide DaemonSet

### Federation appliance (on-prem k3s)

```sh
./scripts/install-prereqs.sh onprem
helm upgrade --install aim-onprem helm/aimvision \
  -f helm/aimvision/values.yaml \
  -f helm/aimvision/values-onprem.yaml \
  --namespace aimvision --create-namespace \
  --wait --timeout=10m
```

What it gives you:
- 2-replica backend, no HPA
- 2-replica Arq workers
- 1-instance CNPG, `local-path` storage, pgBackRest local backup
- MinIO StatefulSet (2Ti) as S3-compatible object store
- Ollama with `deepseek-coder-v2:14b-q4_k_m`, GPU node selector
- SealedSecrets controller (air-gappable)
- ServiceMonitor enabled — in-cluster Prometheus scrapes /metrics

### Dev (kind / k3d laptop loop)

```sh
./scripts/install-prereqs.sh dev
helm upgrade --install aim-dev helm/aimvision \
  -f helm/aimvision/values.yaml \
  -f helm/aimvision/values-dev.yaml \
  --namespace aimvision --create-namespace
```

Tiny resource footprint, no autoscaling, no NetworkPolicies, plain HTTP via
`*.127.0.0.1.nip.io`. Optional Ollama (set `ollama.enabled: true` in a local
override if you have a GPU on the laptop).

---

## Verifying

```sh
helm lint helm/aimvision --strict
kubectl -n aimvision get pods,svc,ingress
kubectl -n aimvision get cluster.postgresql.cnpg.io
kubectl -n aimvision describe externalsecret aimvision-backend-secrets   # cloud
kubectl -n aimvision describe sealedsecret aimvision-backend-secrets    # on-prem
helm test -n aimvision aim-cloud
```

---

## Where things live

| Concern                       | File                                                                |
| ----------------------------- | ------------------------------------------------------------------- |
| Which images / replicas       | `helm/aimvision/values*.yaml`                                       |
| What the backend Deployment looks like | `helm/aimvision/templates/backend-deployment.yaml`         |
| The Postgres Cluster CR       | `helm/aimvision/templates/cnpg-cluster.yaml`                        |
| Default-deny network policies | `helm/aimvision/templates/networkpolicy.yaml`                       |
| TLS / cert-manager wiring     | `helm/aimvision/templates/backend-ingress.yaml`, web-ingress.yaml   |
| Secret provider (sealed/ESO)  | `helm/aimvision/templates/secrets-external.yaml`                    |
| Prometheus scrape             | `helm/aimvision/templates/servicemonitor.yaml`                      |
| Health-check                  | `helm/aimvision/tests/test-connection.yaml`                         |

## References

- [ADR-0005 — CloudNativePG + single Helm chart for cloud↔on-prem parity](../docs/adr/0005-cloudnativepg-cloud-onprem-parity.md)
- [Architecture overview §3.6 / §6](../docs/architecture-overview.md)
- [docs/security/multi-tenant-isolation.md](../docs/security/multi-tenant-isolation.md)
- [docs/observability-plan.md](../docs/observability-plan.md)
