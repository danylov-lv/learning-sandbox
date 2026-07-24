{{/* Release-name-prefixed resource name, truncated to 63 chars. */}}
{{- define "t18-workload.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Selector labels -- must stay stable across chart version bumps (used as an immutable Deployment/Service selector). */}}
{{- define "t18-workload.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* Standard label set applied to every resource in this chart. */}}
{{- define "t18-workload.labels" -}}
{{ include "t18-workload.selectorLabels" . }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}
