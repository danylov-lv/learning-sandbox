{{/*
queue-chart.fullname -- the name this subchart's Service is reachable at.
Deliberately independent of .Values.fullnameOverride gymnastics: it only
uses .Release.Name, which Helm shares between a parent chart and every
subchart it pulls in, so a parent template can call this same named
template (Helm's template namespace is global across parent + subcharts)
to compute the exact same string without needing its own copy of it.
*/}}
{{- define "queue-chart.fullname" -}}
{{- .Release.Name }}-queue-chart
{{- end -}}

{{/*
queue-chart.labels -- the label set applied to every resource this
subchart renders, and used as this subchart's pod selector.
*/}}
{{- define "queue-chart.labels" -}}
app.kubernetes.io/name: queue-chart
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
