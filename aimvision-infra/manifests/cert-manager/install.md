# cert-manager — install prerequisite

AIMVISION ingresses request TLS via cert-manager `ClusterIssuer`s referenced
by annotation:

- Cloud: `cert-manager.io/cluster-issuer: letsencrypt-prod`
- On-prem: `cert-manager.io/cluster-issuer: aimvision-internal-ca`

cert-manager must be installed cluster-wide before applying the AIMVISION
chart, otherwise the Ingresses are valid but no Certificate is provisioned.

## Install (Helm)

```sh
helm repo add jetstack https://charts.jetstack.io
helm repo update
helm upgrade --install cert-manager \
  --namespace cert-manager --create-namespace \
  --version v1.15.3 \
  --set installCRDs=true \
  jetstack/cert-manager
```

## ClusterIssuer — cloud (Let's Encrypt)

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: ops@aimvision.io
    privateKeySecretRef:
      name: letsencrypt-prod-account-key
    solvers:
      - http01:
          ingress:
            class: nginx
```

## ClusterIssuer — on-prem (private CA)

The federation appliance bundle ships a self-signed root CA that lives in a
SealedSecret named `aimvision-internal-ca`. cert-manager issues from it for
the LAN-only `*.aimvision.local` hostnames.

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: aimvision-internal-ca
spec:
  ca:
    secretName: aimvision-internal-ca
```

## Verifying

```sh
kubectl get pods -n cert-manager
kubectl get clusterissuer
kubectl describe clusterissuer letsencrypt-prod   # cloud
kubectl describe clusterissuer aimvision-internal-ca # on-prem
```
