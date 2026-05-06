# CloudNativePG operator — install prerequisite

The AIMVISION chart ships a `Cluster` CR (`postgresql.cnpg.io/v1`) but assumes
the **CloudNativePG operator** is already installed cluster-wide. Per ADR-0005
this operator drives the Postgres lifecycle identically in cloud and on-prem.

## Recommended: Helm install

```sh
helm repo add cnpg https://cloudnative-pg.github.io/charts
helm repo update
helm upgrade --install cnpg \
  --namespace cnpg-system --create-namespace \
  --version 0.22.1 \
  cnpg/cloudnative-pg
```

The version above is pinned. Bump when you intentionally upgrade — the operator
is the only component touching primary failover, so bumps are coordinated with
SRE and tested on staging first (see `docs/operations/runbooks/cnpg-upgrade.md`).

## Air-gapped install (federation appliance)

For air-gapped federation appliances, vendor the operator manifest into the
appliance bundle:

```sh
# at build time:
helm template cnpg cnpg/cloudnative-pg --version 0.22.1 \
  --namespace cnpg-system > install.yaml

# at install time on the appliance:
kubectl create namespace cnpg-system --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n cnpg-system -f install.yaml
```

The `install.yaml` file is intentionally NOT committed to git — it is regenerated
on each appliance image build, and the image build is reproducible.

## Verifying

```sh
kubectl -n cnpg-system get deploy cnpg-controller-manager
kubectl -n cnpg-system rollout status deploy/cnpg-controller-manager --timeout=120s
kubectl get crd | grep cnpg
# Expect: backups.postgresql.cnpg.io, clusters.postgresql.cnpg.io,
#         poolers.postgresql.cnpg.io, scheduledbackups.postgresql.cnpg.io
```

Once the CRDs are present, applying the AIMVISION chart will create a `Cluster`
resource that the operator reconciles.
