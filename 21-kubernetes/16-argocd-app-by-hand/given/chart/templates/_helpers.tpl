{{/* Release-name-prefixed resource name, truncated to 63 chars. */}}
{{- define "sandbox20-fixture.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Selector labels -- must stay stable across chart version bumps (used as an immutable Deployment/Service selector). */}}
{{- define "sandbox20-fixture.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* Standard label set applied to every resource in this chart. */}}
{{- define "sandbox20-fixture.labels" -}}
{{ include "sandbox20-fixture.selectorLabels" . }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}
