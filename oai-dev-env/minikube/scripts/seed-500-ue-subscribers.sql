-- SPDX-License-Identifier: MIT
-- Idempotent live seed for the five-region PacketRusher development profile.
-- Covers SUPIs 001010000000100 through 001010000000599.

INSERT IGNORE INTO `AuthenticationSubscription`
  (`ueid`, `authenticationMethod`, `encPermanentKey`, `protectionParameterId`, `sequenceNumber`, `authenticationManagementField`, `algorithmId`, `encOpcKey`, `encTopcKey`, `vectorGenerationInHss`, `n5gcAuthMethod`, `rgAuthenticationInd`, `supi`)
WITH RECURSIVE seq(n) AS (
  SELECT 100
  UNION ALL
  SELECT n + 1 FROM seq WHERE n < 599
)
SELECT
  CONCAT('001010000000', LPAD(n, 3, '0')),
  '5G_AKA',
  'fec86ba6eb707ed08905757b1bb44b8f',
  'fec86ba6eb707ed08905757b1bb44b8f',
  '{\"sqn\": \"000000000020\", \"sqnScheme\": \"NON_TIME_BASED\", \"lastIndexes\": {\"ausf\": 0}}',
  '8000',
  'milenage',
  'C42449363BBAD02B66D16BC975D77CC1',
  NULL,
  NULL,
  NULL,
  NULL,
  CONCAT('001010000000', LPAD(n, 3, '0'))
FROM seq;

INSERT IGNORE INTO `SessionManagementSubscriptionData`
  (`ueid`, `servingPlmnid`, `singleNssai`, `dnnConfigurations`)
WITH RECURSIVE seq(n) AS (
  SELECT 100
  UNION ALL
  SELECT n + 1 FROM seq WHERE n < 599
)
SELECT
  CONCAT('001010000000', LPAD(n, 3, '0')),
  '00101',
  '{\"sst\": 1, \"sd\": \"FFFFFF\"}',
  '{\"oai\":{\"pduSessionTypes\":{\"defaultSessionType\":\"IPV4\"},\"sscModes\":{\"defaultSscMode\":\"SSC_MODE_1\"},\"5gQosProfile\":{\"5qi\":6,\"arp\":{\"priorityLevel\":1,\"preemptCap\":\"NOT_PREEMPT\",\"preemptVuln\":\"NOT_PREEMPTABLE\"},\"priorityLevel\":1},\"sessionAmbr\":{\"uplink\":\"1000Mbps\",\"downlink\":\"1000Mbps\"}}}'
FROM seq;
