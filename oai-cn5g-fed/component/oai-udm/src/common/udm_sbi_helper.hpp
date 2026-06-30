/*
 * Licensed to the OpenAirInterface (OAI) Software Alliance under one or more
 * contributor license agreements.  See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.
 * The OpenAirInterface Software Alliance licenses this file to You under
 * the OAI Public License, Version 1.1  (the "License"); you may not use this
 * file except in compliance with the License. You may obtain a copy of the
 * License at
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

#pragma once

#include <nlohmann/json.hpp>

#include "PlmnId.h"
#include "sbi_helper.hpp"
#include "udm_config.hpp"

using namespace oai::udm::config;
using namespace oai::common::sbi;

extern udm_config udm_cfg;

namespace oai::udm::api {

class udm_sbi_helper : public sbi_helper {
 public:
  static inline const std::string SubscriberDataManagementServiceBase =
      sbi_helper::UdmSdmBase +
      udm_cfg.sbi.api_version.value_or(kDefaultSbiApiVersion);
  static inline const std::string ContextManagementServiceBase =
      sbi_helper::UdmUeCmBase +
      udm_cfg.sbi.api_version.value_or(kDefaultSbiApiVersion);
  static inline const std::string UeAuthenticationServiceBase =
      sbi_helper::UdmUeAuBase +
      udm_cfg.sbi.api_version.value_or(kDefaultSbiApiVersion);
  static inline const std::string EventExposureServiceBase =
      sbi_helper::UdmEeBase +
      udm_cfg.sbi.api_version.value_or(kDefaultSbiApiVersion);
  static void set_problem_details(
      nlohmann::json& json_data, const std::string& detail);
  static std::string get_udr_slice_selection_subscription_data_retrieval_uri(
      const std::string& supi, const oai::model::common::PlmnId& plmn_id);
  static std::string get_udr_access_and_mobility_subscription_data_uri(
      const std::string& supi, const oai::model::common::PlmnId& plmn_id);
  static std::string get_udr_session_management_subscription_data_uri(
      const std::string& supi, const oai::model::common::PlmnId& plmn_id);
  static std::string get_udr_smf_selection_subscription_data_uri(
      const std::string& supi, const oai::model::common::PlmnId& plmn_id);
  static std::string get_udr_uri_base();
  static std::string get_udr_sdm_subscriptions_uri(const std::string& supi);
  static std::string get_udr_authentication_subscription_uri(
      const std::string& supi);
  static std::string get_udr_authentication_status_uri(const std::string& supi);
  static std::string get_udr_amf_3gpp_registration_uri(const std::string& supi);
  static std::string get_udm_ueau_base();
};

}  // namespace oai::udm::api
