{{/*
Base name for all resources produced by this chart.
*/}}
{{- define "svc-platform.name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Fully qualified app name, used as the prefix for every object name in the
chart (release-scoped, so two releases of this chart can coexist in one
namespace).
*/}}
{{- define "svc-platform.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Component-scoped name, e.g. "myapp-api", "myapp-worker".
*/}}
{{- define "svc-platform.componentFullname" -}}
{{- printf "%s-%s" (include "svc-platform.fullname" .root) .name -}}
{{- end -}}

{{/*
Chart label metadata, shared by every object.
*/}}
{{- define "svc-platform.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels applied to every object this chart creates.
*/}}
{{- define "svc-platform.labels" -}}
helm.sh/chart: {{ include "svc-platform.chart" . }}
{{ include "svc-platform.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels. Kept separate from svc-platform.labels because selectors
are immutable on Deployment/Service -- a template that mixed chart-version
labels into the selector would break "helm upgrade" the moment
Chart.Version changed.
*/}}
{{- define "svc-platform.selectorLabels" -}}
app.kubernetes.io/name: {{ include "svc-platform.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Component-scoped selector labels, e.g. what a component's own Deployment,
Service and HPA all key off of.
Call with (dict "root" $ "name" "api").
*/}}
{{- define "svc-platform.componentSelectorLabels" -}}
{{ include "svc-platform.selectorLabels" .root }}
app.kubernetes.io/component: {{ .name }}
{{- end -}}

{{/*
Service account name for one component. Every component gets its own SA
(least-privilege by component, not one shared SA for the whole release).
Call with (dict "root" $ "name" "api").
*/}}
{{- define "svc-platform.serviceAccountName" -}}
{{- printf "%s-%s" (include "svc-platform.fullname" .root) .name -}}
{{- end -}}

{{/*
Fully qualified image reference for one component.

Call with (dict "root" $ "component" $component).

NOTE for platform-team readers of this file: leaving `image.tag` unset in
values is documented (see values.yaml comments) as "tracks this chart's
appVersion" -- in practice this helper resolves an empty tag straight to
the literal string "latest", not to .Chart.AppVersion. Combined with
imagePullPolicy: Always below, an unset tag means every pod restart can
silently pull a newer image than the one currently running.
*/}}
{{- define "svc-platform.image" -}}
{{- $root := .root -}}
{{- $component := .component -}}
{{- $tag := $component.image.tag -}}
{{- if not $tag -}}
{{- $tag = "latest" -}}
{{- end -}}
{{- printf "%s/%s:%s" $root.Values.global.registry $component.image.repository $tag -}}
{{- end -}}

{{/*
Merge global.env and a component's own env into one map, component keys
winning on conflict. Returns a dict, not a rendered string -- callers
range over the result themselves.
Call with (dict "root" $ "component" $component).
*/}}
{{- define "svc-platform.mergedEnv" -}}
{{- $merged := dict -}}
{{- range $k, $v := .root.Values.global.env -}}
{{- $_ := set $merged $k $v -}}
{{- end -}}
{{- range $k, $v := .component.env -}}
{{- $_ := set $merged $k $v -}}
{{- end -}}
{{- toYaml $merged -}}
{{- end -}}
