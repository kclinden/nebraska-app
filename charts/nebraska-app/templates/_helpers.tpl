{{- define "nebraska-app.fullname" -}}
{{- printf "%s" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "nebraska-app.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{- define "nebraska-app.selector" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "nebraska-app.dynamodbEndpoint" -}}
{{- if .Values.dynamodb.enabled -}}
http://{{ include "nebraska-app.fullname" . }}-dynamodb:8000
{{- else -}}
{{ required "dynamodb.externalEndpoint is required when dynamodb.enabled=false" .Values.dynamodb.externalEndpoint }}
{{- end -}}
{{- end -}}

{{- define "nebraska-app.restrictedContainer" -}}
allowPrivilegeEscalation: false
capabilities:
  drop: ["ALL"]
{{- end -}}
