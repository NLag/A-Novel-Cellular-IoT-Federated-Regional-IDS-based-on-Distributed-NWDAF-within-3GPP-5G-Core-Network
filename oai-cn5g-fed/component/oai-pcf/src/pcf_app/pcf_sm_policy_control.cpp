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

/*! \file pcf_sm_policy_control.cpp
 \brief
 \author  Rohan Kharade
 \company Openairinterface Software Allianse
 \date 2021
 \email: rohan.kharade@openairinterface.org
 */

#include "pcf_sm_policy_control.hpp"
#include "logger.hpp"
#include "pcf_config.hpp"
#include "sm_policy/policy_decision.hpp"
#include "http_client.hpp"
#include "TrafficControlData.h"

#include <boost/uuid/uuid_io.hpp>
#include <algorithm>
#include <unordered_map>
#include <map>
#include <memory>
#include <string>

using namespace oai::pcf::app;
using namespace oai::pcf::app::sm_policy;
using namespace oai::config::pcf;
using namespace oai::model::pcf;
using namespace oai::common::sbi;
using namespace oai::http;

using namespace std;

extern std::shared_ptr<oai::http::http_client> http_client_inst;

namespace {
constexpr auto IDS_DUPLICATION_RULE_ID = "ids-duplication";

bool ids_traffic_influence_active = false;

bool is_ids_traffic_influence_request(const SmPolicyContextData& context) {
  const auto notification_uri = context.getNotificationUri();
  return notification_uri.find("oai-ids") != std::string::npos ||
         notification_uri.find("/nids-") != std::string::npos;
}

bool decision_contains_ids_duplication_rule(
    const SmPolicyDecision& sm_policy_decision) {
  if (!sm_policy_decision.pccRulesIsSet()) {
    return false;
  }

  for (const auto& rule : sm_policy_decision.getPccRules()) {
    if (rule.first == IDS_DUPLICATION_RULE_ID ||
        rule.second.getPccRuleId() == IDS_DUPLICATION_RULE_ID) {
      return true;
    }
  }

  return false;
}

SmPolicyDecision without_ids_duplication_rule(const SmPolicyDecision& input) {
  SmPolicyDecision decision = input;
  if (!decision.pccRulesIsSet()) {
    return decision;
  }

  std::vector<std::string> ids_tc_refs;
  auto pcc_rules = decision.getPccRules();
  for (auto it = pcc_rules.begin(); it != pcc_rules.end();) {
    if (it->first == IDS_DUPLICATION_RULE_ID ||
        it->second.getPccRuleId() == IDS_DUPLICATION_RULE_ID) {
      if (it->second.refTcDataIsSet()) {
        for (const auto& tc_ref : it->second.getRefTcData()) {
          ids_tc_refs.push_back(tc_ref);
        }
      }
      it = pcc_rules.erase(it);
    } else {
      ++it;
    }
  }
  decision.setPccRules(pcc_rules);

  if (decision.traffContDecsIsSet() && !ids_tc_refs.empty()) {
    auto traffic_controls = decision.getTraffContDecs();
    for (const auto& tc_ref : ids_tc_refs) {
      traffic_controls.erase(tc_ref);
    }
    decision.setTraffContDecs(traffic_controls);
  }

  return decision;
}

bool is_smf_policy_request(const SmPolicyContextData& context) {
  const auto notification_uri = context.getNotificationUri();
  return !notification_uri.empty() &&
         notification_uri.find("oai-smf") != std::string::npos;
}
}  // namespace

//------------------------------------------------------------------------------
pcf_smpc::pcf_smpc(
    const std::shared_ptr<oai::pcf::app::sm_policy::policy_storage>&
        policy_storage) {
  m_policy_storage = policy_storage;

  std::function<void(const std::shared_ptr<policy_decision>& decision)> f =
      std::bind(&pcf_smpc::handle_policy_change, this, std::placeholders::_1);

  m_policy_storage->subscribe_to_decision_change(f);
}

void pcf_smpc::handle_policy_change(
    const std::shared_ptr<policy_decision>& /* decision */) {
  Logger::pcf_app().warn("Policy changed, but not implemented!");
}

//------------------------------------------------------------------------------
status_code pcf_smpc::create_sm_policy_handler(
    const SmPolicyContextData& context, SmPolicyDecision& decision,
    std::string& association_id, std::string& problem_details) {
  std::shared_ptr<policy_decision> chosen_decision =
      m_policy_storage->find_policy(context);

  if (!chosen_decision) {
    problem_details = fmt::format(
        "SM policy request from SUPI {}: No policies found", context.getSupi());
    return status_code::CONTEXT_DENIED;
  }

  association_id = std::to_string(m_association_id_generator.get_uid());

  individual_sm_association assoc(context, *chosen_decision, association_id);

  status_code res = assoc.decide_policy(decision);
  const bool ids_request = is_ids_traffic_influence_request(context);
  const bool ids_rule = decision_contains_ids_duplication_rule(decision);

  if (res != status_code::CREATED) {
    problem_details = fmt::format(
        "SM Policy request from SUPI {}: Invalid policy decision provisioned",
        context.getSupi());
  } else {
    if (ids_rule && !ids_traffic_influence_active && !ids_request) {
      decision = without_ids_duplication_rule(decision);
      Logger::pcf_app().info(fmt::format(
          "IDS traffic influence inactive for SUPI {}; return normal "
          "decision without PCC rule {}",
          context.getSupi(), IDS_DUPLICATION_RULE_ID));
    }

    std::unique_lock lock_assocations(m_associations_mutex);
    m_associations.insert(std::make_pair(association_id, assoc));

    Logger::pcf_app().info(fmt::format(
        "Created Policy Decision for SUPI {} with ID {}", context.getSupi(),
        association_id));
  }
  return res;
}

//------------------------------------------------------------------------------
sm_policy::status_code pcf_smpc::delete_sm_policy_handler(
    const std::string& id, const SmPolicyDeleteData& /* delete_data */,
    std::string& problem_details) {
  // TODO for now, just delete, ignore the delete_data
  std::unique_lock lock_associations(m_associations_mutex);
  auto iter = m_associations.find(id);
  if (iter == m_associations.end()) {
    problem_details =
        fmt::format("Could not delete policy association: ID {} not found", id);
    Logger::pcf_app().info(problem_details);
    return status_code::NOT_FOUND;
  }
  m_associations.erase(iter);
  Logger::pcf_app().info(
      fmt::format("Deleted policy association with ID {}", id));

  return status_code::OK;
}

//------------------------------------------------------------------------------
sm_policy::status_code pcf_smpc::get_sm_policy_handler(
    const std::string& id, SmPolicyControl& control,
    std::string& problem_details) {
  std::shared_lock lock_associations(m_associations_mutex);
  auto iter = m_associations.find(id);
  if (iter == m_associations.end()) {
    problem_details = fmt::format(
        "Could not retrieve policy association: ID {} not found", id);
    Logger::pcf_app().info(problem_details);
    return status_code::NOT_FOUND;
  }
  control.setContext(iter->second.get_sm_policy_context_data());
  control.setPolicy(iter->second.get_sm_policy_decision_dto());

  Logger::pcf_app().info(
      fmt::format("Retrieved policy association with ID {}", id));

  return status_code::OK;
}

//------------------------------------------------------------------------------
sm_policy::status_code pcf_smpc::update_sm_policy_handler(
    const std::string& id, const SmPolicyUpdateContextData& update_context,
    SmPolicyDecision& decision, std::string& problem_details) {
  std::unique_lock lock_associations(m_associations_mutex);
  auto iter = m_associations.find(id);

  if (iter == m_associations.end()) {
    problem_details =
        fmt::format("Could not update policy association: ID {} not found", id);
    Logger::pcf_app().info(problem_details);
    return status_code::NOT_FOUND;
  }

  SmPolicyDecision new_decision;

  return iter->second.redecide_policy(
      update_context, decision, problem_details);
}

//------------------------------------------------------------------------------
std::string pcf_smpc::ids_traffic_influence_status_handler() {
  nlohmann::json body = {
      {"idsTrafficInfluenceActive", ids_traffic_influence_active},
      {"pccRuleId", IDS_DUPLICATION_RULE_ID},
      {"changed", false},
  };
  return body.dump();
}

//------------------------------------------------------------------------------
std::string pcf_smpc::ids_traffic_influence_handler(bool active) {
  const bool changed = ids_traffic_influence_active != active;
  ids_traffic_influence_active = active;

  if (changed) {
    Logger::pcf_app().info(fmt::format(
        "IDS traffic influence {} by IDS notification",
        active ? "activated" : "deactivated"));
  } else {
    Logger::pcf_app().info(fmt::format(
        "IDS traffic influence refresh from IDS notification: active={}",
        active));
  }

  if (changed) {
    notify_ids_traffic_influence_change(active);
  }

  nlohmann::json body = {
      {"idsTrafficInfluenceActive", ids_traffic_influence_active},
      {"pccRuleId", IDS_DUPLICATION_RULE_ID},
      {"changed", changed},
  };
  return body.dump();
}

//------------------------------------------------------------------------------
void pcf_smpc::notify_ids_traffic_influence_change(bool active) {
  std::shared_lock lock_associations(m_associations_mutex);
  for (const auto& association : m_associations) {
    const auto& context = association.second.get_sm_policy_context_data();
    if (!is_smf_policy_request(context)) {
      continue;
    }

    const auto notification_uri = context.getNotificationUri();
    SmPolicyDecision decision = association.second.get_sm_policy_decision_dto();
    if (!active) {
      decision = without_ids_duplication_rule(decision);
    }

    nlohmann::json payload;
    payload["resourceUri"] = association.first;
    payload["smPolicyDecision"] = decision;

    try {
      auto req = http_client_inst->prepare_json_request(
          notification_uri, payload.dump());
      auto resp = http_client_inst->send_http_request(method_e::POST, req);
      Logger::pcf_app().info(fmt::format(
          "Sent IDS traffic influence notification active={} to {}: HTTP {}",
          active, notification_uri, static_cast<int>(resp.status_code)));
    } catch (const std::exception& e) {
      Logger::pcf_app().warn(fmt::format(
          "Failed to notify SMF IDS traffic influence change at {}: {}",
          notification_uri, e.what()));
    }
  }
}

//------------------------------------------------------------------------------
pcf_smpc::~pcf_smpc() {
  Logger::pcf_app().debug("Delete PCF SMPC instance...");
}
