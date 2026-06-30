{{- define "oai-nwdaf-dev.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name (.Chart.Version | replace "+" "_") }}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
nwdaf.oai/region: {{ .Values.global.region | quote }}
nwdaf.oai/tac: {{ .Values.global.tac | quote }}
{{- end }}

{{- define "oai-nwdaf-dev.podImagePullSecrets" -}}
{{- if .Values.global.imagePullSecrets }}
imagePullSecrets:
{{ toYaml .Values.global.imagePullSecrets | indent 2 }}
{{- end }}
{{- end }}

{{- define "oai-nwdaf-dev.sharedStorageMount" -}}
{{- if .Values.global.sharedStorage.enabled }}
- name: oai-5g-storage
  mountPath: {{ .Values.global.sharedStorage.mountPath | quote }}
{{- end }}
{{- end }}

{{- define "oai-nwdaf-dev.sharedStorageVolume" -}}
{{- if .Values.global.sharedStorage.enabled }}
- name: oai-5g-storage
  {{- if .Values.global.sharedStorage.existingClaim }}
  persistentVolumeClaim:
    claimName: {{ .Values.global.sharedStorage.existingClaim | quote }}
  {{- else if .Values.global.sharedStorage.hostPath }}
  hostPath:
    path: {{ .Values.global.sharedStorage.hostPath | quote }}
    type: {{ .Values.global.sharedStorage.hostPathType | quote }}
  {{- else }}
  emptyDir: {}
  {{- end }}
{{- end }}
{{- end }}
