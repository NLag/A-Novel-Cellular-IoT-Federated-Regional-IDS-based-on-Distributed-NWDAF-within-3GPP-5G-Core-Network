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

#ifndef _UDM_CONFIG_H_
#define _UDM_CONFIG_H_

#include "udm.h"
#include "udm_config.hpp"

using namespace oai::common::sbi;
namespace oai::udm::config {

class udm_config {
 public:
  udm_config();
  ~udm_config();

  unsigned int instance;
  std::string pid_dir;
  std::string udm_name;
  spdlog::level::level_enum log_level;

  interface_cfg_t sbi;
  nf_addr_t udr_addr;
  nf_addr_t nrf_addr;

  bool register_nrf;
  bool use_http2;
  uint32_t http_request_timeout;
};

}  // namespace oai::udm::config

#endif
