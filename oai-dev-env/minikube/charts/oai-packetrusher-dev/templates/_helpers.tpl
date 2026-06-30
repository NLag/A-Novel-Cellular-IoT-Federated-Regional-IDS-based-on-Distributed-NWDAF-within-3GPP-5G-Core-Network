{{- define "oai-packetrusher-dev.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name (.Chart.Version | replace "+" "_") }}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "oai-packetrusher-dev.selectorLabels" -}}
app.kubernetes.io/name: {{ .root.Chart.Name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: packetrusher-region
app.kubernetes.io/region: {{ .region.name }}
{{- end }}

{{- define "oai-packetrusher-dev.fullname" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "oai-packetrusher-dev.regionName" -}}
{{- printf "%s-%s" (include "oai-packetrusher-dev.fullname" .root) .region.name | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "oai-packetrusher-dev.configName" -}}
{{- printf "%s-config" (include "oai-packetrusher-dev.regionName" .) | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "oai-packetrusher-dev.podImagePullSecrets" -}}
{{- if .Values.global.imagePullSecrets }}
imagePullSecrets:
{{ toYaml .Values.global.imagePullSecrets | indent 2 }}
{{- end }}
{{- end }}

{{- define "oai-packetrusher-dev.regionMsin" -}}
{{- printf "%010d" (int .region.msinStart) -}}
{{- end }}
