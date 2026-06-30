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

#ifndef _UDR_CONFIG_H_
#define _UDR_CONFIG_H_

#include <string>

#include "udr.h"
#include "logger.hpp"
#include "sbi_helper.hpp"

namespace oai::udr::config {

typedef struct {
  std::string server;
  uint32_t port;
  std::string user;
  std::string pass;
  std::string db_name;
  uint32_t connection_timeout;
} db_conf_t;

class udr_config {
 public:
  udr_config();
  ~udr_config();

  unsigned int instance;
  std::string pid_dir;
  std::string udr_name;
  spdlog::level::level_enum log_level;
  oai::common::sbi::interface_cfg_t nudr;
  oai::common::sbi::nf_addr_t nrf_addr;
  bool register_nrf;
  bool use_http2;
  uint32_t http_request_timeout;
  db_conf_t db_conf;
  db_type_t db_type;
};
}  // namespace oai::udr::config

#endif
