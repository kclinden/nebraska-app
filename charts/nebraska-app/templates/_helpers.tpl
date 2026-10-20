{{- define "nebraska-app.fullname" -}}
{{- printf "%s" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "nebraska-app.labels" -}}
Application: {{ .Values.applicationName | quote }}
app.kubernetes.io/part-of: {{ .Values.applicationName | lower | quote }}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{- define "nebraska-app.annotations" -}}
Application: {{ .Values.applicationName | quote }}
app.kubernetes.io/part-of: {{ .Values.applicationName | lower | quote }}
{{- end -}}

{{- define "nebraska-app.selector" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "nebraska-app.dynamodbEndpoint" -}}
{{- if .Values.dynamodb.enabled -}}
http://{{ include "nebraska-app.fullname" . }}-dynamodb:8000
{{- else -}}
{{ .Values.dynamodb.externalEndpoint }}
{{- end -}}
{{- end -}}

{{- define "nebraska-app.serviceAccount" -}}
{{- .Values.serviceAccount.name | default (include "nebraska-app.fullname" .) -}}
{{- end -}}

{{- define "nebraska-app.restrictedContainer" -}}
allowPrivilegeEscalation: false
capabilities:
  drop: ["ALL"]
{{- end -}}

{{- define "nebraska-app.syncPod" -}}
restartPolicy: Never
{{- if or .Values.serviceAccount.create .Values.serviceAccount.name }}
serviceAccountName: {{ include "nebraska-app.serviceAccount" . }}
{{- end }}
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  seccompProfile:
    type: RuntimeDefault
containers:
  - name: espn-sync
    image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
    imagePullPolicy: {{ .Values.image.pullPolicy }}
    command: ["python", "-m", "espn"]
    envFrom:
      - secretRef:
          name: {{ include "nebraska-app.fullname" . }}-aws
    env:
      - name: ESPN_SEASON
        value: {{ .Values.sportsData.season | quote }}
    resources:
      requests:
        cpu: 100m
        memory: 128Mi
      limits:
        memory: 512Mi
    securityContext:
      {{- include "nebraska-app.restrictedContainer" . | nindent 6 }}
{{- end -}}
