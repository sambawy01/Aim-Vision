{{/*
=============================================================================
AIMVISION Helm helpers
-----------------------------------------------------------------------------
Standard Helm helper boilerplate plus AIMVISION-specific helpers (image refs
that respect global.imageRegistry, common labels, common annotations).

See ADR-0005 for the cloud↔on-prem parity model. Anything that needs to
behave differently between tiers should be value-driven, NOT template-branched
on a tier string. Helpers below take a `tier` indirectly only because the
release labels include it.
=============================================================================
*/}}

{{/* -------------------------------------------------------------------- */}}
{{/* Names                                                                */}}
{{/* -------------------------------------------------------------------- */}}

{{/*
Expand the name of the chart.
*/}}
{{- define "aimvision.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to
this (by the DNS naming spec).
*/}}
{{- define "aimvision.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Component-specific full names (deployment / service / configmap names share these).
*/}}
{{- define "aimvision.backend.fullname" -}}
{{- printf "%s-backend" (include "aimvision.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "aimvision.worker.fullname" -}}
{{- printf "%s-worker" (include "aimvision.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "aimvision.web.fullname" -}}
{{- printf "%s-web" (include "aimvision.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "aimvision.minio.fullname" -}}
{{- printf "%s-minio" (include "aimvision.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "aimvision.ollama.fullname" -}}
{{- printf "%s-ollama" (include "aimvision.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "aimvision.temporal.fullname" -}}
{{- printf "%s-temporal" (include "aimvision.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "aimvision.cnpg.fullname" -}}
{{- default (printf "%s-pg" (include "aimvision.fullname" .)) .Values.cnpg.clusterName | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "aimvision.config.fullname" -}}
{{- printf "%s-config" (include "aimvision.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "aimvision.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* -------------------------------------------------------------------- */}}
{{/* Labels & selectors                                                   */}}
{{/* -------------------------------------------------------------------- */}}

{{/*
Common labels — applied to every resource produced by this chart.
*/}}
{{- define "aimvision.labels" -}}
helm.sh/chart: {{ include "aimvision.chart" . }}
{{ include "aimvision.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
aimvision.io/tier: {{ .Values.global.tier | default "cloud" | quote }}
{{- with .Values.global.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Selector labels — *immutable* across upgrades. Do NOT add chart version here.
*/}}
{{- define "aimvision.selectorLabels" -}}
app.kubernetes.io/name: {{ include "aimvision.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Component-scoped selector labels — used by Deployment.spec.selector and
Service.spec.selector to tie a workload to its pods.
*/}}
{{- define "aimvision.backend.selectorLabels" -}}
{{ include "aimvision.selectorLabels" . }}
app.kubernetes.io/component: backend
{{- end }}

{{- define "aimvision.worker.selectorLabels" -}}
{{ include "aimvision.selectorLabels" . }}
app.kubernetes.io/component: worker
{{- end }}

{{- define "aimvision.web.selectorLabels" -}}
{{ include "aimvision.selectorLabels" . }}
app.kubernetes.io/component: web
{{- end }}

{{- define "aimvision.minio.selectorLabels" -}}
{{ include "aimvision.selectorLabels" . }}
app.kubernetes.io/component: minio
{{- end }}

{{- define "aimvision.ollama.selectorLabels" -}}
{{ include "aimvision.selectorLabels" . }}
app.kubernetes.io/component: ollama
{{- end }}

{{- define "aimvision.temporal.selectorLabels" -}}
{{ include "aimvision.selectorLabels" . }}
app.kubernetes.io/component: temporal
{{- end }}

{{/*
Common annotations.
*/}}
{{- define "aimvision.annotations" -}}
{{- with .Values.global.commonAnnotations }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/* -------------------------------------------------------------------- */}}
{{/* Image references                                                     */}}
{{/* -------------------------------------------------------------------- */}}

{{/*
Render an image reference, honouring global.imageRegistry as an optional prefix.
Usage:
  {{ include "aimvision.image" (dict "image" .Values.backend.image "global" .Values.global) }}
*/}}
{{- define "aimvision.image" -}}
{{- $registry := .global.imageRegistry | default "" -}}
{{- $repo := .image.repository -}}
{{- $tag := .image.tag | default "latest" -}}
{{- if $registry -}}
{{ printf "%s/%s:%s" $registry $repo $tag }}
{{- else -}}
{{ printf "%s:%s" $repo $tag }}
{{- end -}}
{{- end }}

{{/*
Image pull secrets (rendered as the imagePullSecrets list).
*/}}
{{- define "aimvision.imagePullSecrets" -}}
{{- with .Values.global.imagePullSecrets -}}
imagePullSecrets:
{{- range . }}
  - name: {{ . }}
{{- end }}
{{- end }}
{{- end }}

{{/* -------------------------------------------------------------------- */}}
{{/* Service-account name (single SA per chart for now)                   */}}
{{/* -------------------------------------------------------------------- */}}

{{- define "aimvision.serviceAccountName" -}}
{{ include "aimvision.fullname" . }}
{{- end }}

{{/* -------------------------------------------------------------------- */}}
{{/* Ingress hostname helper — values pass literal hosts in v0.1.0,       */}}
{{/* but this helper exists so we can eventually template "api.{{.domain}}" */}}
{{/* without re-evaluating values strings.                                */}}
{{/* -------------------------------------------------------------------- */}}

{{- define "aimvision.backend.host" -}}
{{- if .Values.backend.ingress.host -}}
{{ .Values.backend.ingress.host }}
{{- else -}}
{{ printf "api.%s" .Values.global.domain }}
{{- end -}}
{{- end }}

{{- define "aimvision.web.host" -}}
{{- if .Values.web.ingress.host -}}
{{ .Values.web.ingress.host }}
{{- else -}}
{{ printf "app.%s" .Values.global.domain }}
{{- end -}}
{{- end }}
