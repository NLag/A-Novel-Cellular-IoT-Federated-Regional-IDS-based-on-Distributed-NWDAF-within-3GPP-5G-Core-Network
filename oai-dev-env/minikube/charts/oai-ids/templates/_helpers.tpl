{{- define "oai-ids.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "oai-ids.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name (.Chart.Version | replace "+" "_") }}
app.kubernetes.io/name: {{ include "oai-ids.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "oai-ids.selectorLabels" -}}
app.kubernetes.io/name: {{ include "oai-ids.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "oai-ids.regionName" -}}
{{- $root := .root -}}
{{- $region := .region -}}
{{- printf "%s-%s" (include "oai-ids.name" $root) $region.name | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "oai-ids.regionConfigName" -}}
{{- printf "%s-config" (include "oai-ids.regionName" .) | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "oai-ids.regionLabels" -}}
{{- $root := .root -}}
{{- $region := .region -}}
{{ include "oai-ids.labels" $root }}
app.kubernetes.io/component: ids-region
app.kubernetes.io/region: {{ $region.name }}
ids.oai/tac: {{ required "region.tac is required in regional IDS mode" $region.tac | quote }}
{{- end }}

{{- define "oai-ids.regionSelectorLabels" -}}
{{- $root := .root -}}
{{- $region := .region -}}
{{ include "oai-ids.selectorLabels" $root }}
app.kubernetes.io/component: ids-region
app.kubernetes.io/region: {{ $region.name }}
{{- end }}

{{- define "oai-ids.regionIdsConfig" -}}
{{- $root := .root -}}
{{- $region := .region -}}
{{- $regionIds := default dict $region.ids -}}
{{- $ids := deepCopy $root.Values.ids -}}
{{- if $regionIds -}}
{{- $ids = mergeOverwrite $ids (deepCopy $regionIds) -}}
{{- end -}}
{{- if not (hasKey $regionIds "host") -}}
{{- $_ := set $ids "host" (default (include "oai-ids.regionName" (dict "root" $root "region" $region)) $region.host) -}}
{{- end -}}
{{- if $region.instanceId -}}
{{- $_ := set $ids "instanceId" $region.instanceId -}}
{{- end -}}
{{- $servingArea := mergeOverwrite (deepCopy (default dict $ids.servingArea)) (deepCopy (default dict $region.servingArea)) -}}
{{- $_ := set $servingArea "region" (default $region.name $servingArea.region) -}}
{{- $_ := set $servingArea "tac" (required "region.tac is required in regional IDS mode" (default $region.tac $servingArea.tac)) -}}
{{- $_ := set $ids "servingArea" $servingArea -}}
{{- $nrf := mergeOverwrite (deepCopy (default dict $ids.nrf)) (deepCopy (default dict $region.nrf)) -}}
{{- if $region.nrfInstanceId -}}
{{- $_ := set $nrf "nf_instance_id" $region.nrfInstanceId -}}
{{- end -}}
{{- $_ := set $ids "nrf" $nrf -}}
{{- $http := default dict $ids.http -}}
{{- $httpPort := default 8080 $http.port -}}
{{- $regionHost := $ids.host -}}
{{- $trafficInfluence := deepCopy (default dict $ids.trafficInfluence) -}}
{{- if not (hasKey (default dict $region.trafficInfluence) "notification_uri") -}}
{{- $_ := set $trafficInfluence "notification_uri" (printf "http://%s:%v/nids-event-exposure/v1/notifications" $regionHost $httpPort) -}}
{{- end -}}
{{- $_ := set $ids "trafficInfluence" $trafficInfluence -}}
{{- $nwdafIntegration := deepCopy (default dict $ids.nwdafIntegration) -}}
{{- if not (hasKey (default dict $region.nwdafIntegration) "notification_uri") -}}
{{- $_ := set $nwdafIntegration "notification_uri" (printf "http://%s:%v/nids-model-management/v1/model-notifications" $regionHost $httpPort) -}}
{{- end -}}
{{- $_ := set $ids "nwdafIntegration" $nwdafIntegration -}}
{{- toYaml $ids -}}
{{- end }}

{{- define "oai-ids.sharedStorageMount" -}}
{{- if .Values.sharedStorage.enabled }}
- name: oai-5g-storage
  mountPath: {{ .Values.sharedStorage.mountPath | quote }}
{{- end }}
{{- end }}

{{- define "oai-ids.sharedStorageVolume" -}}
{{- if .Values.sharedStorage.enabled }}
- name: oai-5g-storage
  {{- if .Values.sharedStorage.existingClaim }}
  persistentVolumeClaim:
    claimName: {{ .Values.sharedStorage.existingClaim | quote }}
  {{- else if .Values.sharedStorage.hostPath }}
  hostPath:
    path: {{ .Values.sharedStorage.hostPath | quote }}
    type: {{ .Values.sharedStorage.hostPathType | quote }}
  {{- else }}
  emptyDir: {}
  {{- end }}
{{- end }}
{{- end }}
