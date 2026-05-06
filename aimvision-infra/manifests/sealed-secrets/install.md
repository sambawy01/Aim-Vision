# sealed-secrets — install prerequisite (on-prem)

The federation on-prem overlay (`values-onprem.yaml`) sets
`secrets.backend.provider = "sealed"`. The `secrets-external.yaml` template
then renders a `SealedSecret`, which the bitnami sealed-secrets controller
decrypts in-cluster into a Kubernetes `Secret`.

Cloud uses **External Secrets Operator** instead (see runbook for ESO
bootstrap); sealed-secrets is the on-prem path because the appliance ships
with a known controller key and tolerates being air-gapped.

## Install (Helm)

```sh
helm repo add sealed-secrets https://bitnami-labs.github.io/sealed-secrets
helm repo update
helm upgrade --install sealed-secrets \
  --namespace kube-system \
  --version 2.16.2 \
  sealed-secrets/sealed-secrets
```

## Sealing a real secret

Once the controller is running, encrypt a `Secret` so it can be committed:

```sh
# Create a plaintext Secret manifest, but DO NOT apply it.
kubectl create secret generic aimvision-backend-secrets \
  --namespace aimvision \
  --from-literal=DATABASE_URL='postgres://aimvision:...@aimvision-pg-rw:5432/aimvision' \
  --from-literal=REDIS_URL='redis://aimvision-redis:6379/0' \
  --from-literal=PASETO_SIGNING_KEY='...' \
  --from-literal=SENTRY_DSN='https://...' \
  --dry-run=client -o yaml > /tmp/backend-secret.yaml

# Encrypt with kubeseal — output goes into values-onprem.yaml under
# secrets.backend.sealed.encryptedData (key->ciphertext map).
kubeseal --controller-namespace=kube-system \
  --controller-name=sealed-secrets \
  --format yaml \
  < /tmp/backend-secret.yaml > /tmp/backend-sealed.yaml

# Inspect; copy spec.encryptedData into the values file.
yq '.spec.encryptedData' /tmp/backend-sealed.yaml
```

Rotate the controller key on a 1-year cadence; previously-sealed values stay
decryptable until you re-seal.

## Verifying

```sh
kubectl -n kube-system get deploy sealed-secrets
kubectl -n kube-system rollout status deploy/sealed-secrets --timeout=120s
kubectl get crd sealedsecrets.bitnami.com
```
