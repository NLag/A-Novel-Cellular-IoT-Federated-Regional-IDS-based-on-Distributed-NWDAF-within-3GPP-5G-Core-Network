/*
 * Licensed to the OpenAirInterface (OAI) Software Alliance under one or more
 * contributor license agreements.  See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.
 * The OpenAirInterface Software Alliance licenses this file to You under
 * the OAI Public License, Version 1.1  (the "License"); you may not use this
 *file except in compliance with the License. You may obtain a copy of the
 *License at
 *
 *      http://www.openairinterface.org/?page_id=698
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *-------------------------------------------------------------------------------
 * For more information about the OpenAirInterface (OAI) Software Alliance:
 *      contact@openairinterface.org
 */

#ifndef FILE_UDM_H_SEEN
#define FILE_UDM_H_SEEN

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>

#include <boost/algorithm/string.hpp>

#include "sbi_helper.hpp"

#define HEART_BEAT_TIMER 10
#define NRF_REGISTRATION_RETRY_TIMER 5

#define _unused(x) ((void) (x))

// Event Subscription IDs)
typedef uint32_t evsub_id_t;
#define EVSUB_ID_FMT "0x%" PRIx32
#define EVSUB_ID_SCAN_FMT SCNx32
#define INVALID_EVSUB_ID ((evsub_id_t) 0x00000000)
#define UNASSIGNED_EVSUB_ID ((evsub_id_t) 0x00000000)

#define NUDM_SDM_SUB "/sdm-subscriptions"
#define NUDM_SMF_SELECT "smf-select-data"
#define NUDM_NSSAI "nssai"
#define NUDM_SM_DATA "sm-data"
#define NUDM_UECM_XGPP_ACCESS "amf-3gpp-access"
#define NUDM_AM_DATA "am-data"
#define NUDM_UE_AU_EVENTS "auth-events"
#define NUDM_UE_AU_GEN_AU_DATA "generate-auth-data"

#endif
