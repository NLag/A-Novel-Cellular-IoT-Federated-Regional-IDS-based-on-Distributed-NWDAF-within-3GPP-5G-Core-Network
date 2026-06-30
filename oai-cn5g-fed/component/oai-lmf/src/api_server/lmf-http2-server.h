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

#ifndef FILE_LMF_HTTP2_SERVER_SEEN
#define FILE_LMF_HTTP2_SERVER_SEEN

#include "conversions.hpp"

#include "lmf_app.hpp"
#include <nghttp2/asio_http2_server.h>
#include "InputData.h"

using namespace nghttp2::asio_http2;
using namespace nghttp2::asio_http2::server;
// using namespace oai::model::lmf;
using namespace oai::lmf::app;

class lmf_http2_server {
 public:
  lmf_http2_server(
      std::string addr, uint32_t port, unsigned num_threads,
      lmf_app* lmf_app_inst)
      : m_address(addr),
        m_port(port),
        m_num_threads(num_threads),
        server(),
        m_lmf_app(lmf_app_inst) {}
  void start();
  void non_ue_n2info_nrppa_notification_post_handler(
      std::vector<mime_part>& parts, const response& response);
  void n2info_nrppa_notification_post_handler(
      const std::string& ueContextId, std::vector<mime_part>& parts,
      const response& response);
  void init(size_t thr) {}

  void detemine_location_post_handler(
      const oai::model::lmf::InputData& inputData, const response& response);

  void stop();

 private:
  std::string m_address;
  uint32_t m_port;
  unsigned m_num_threads;
  http2 server;
  lmf_app* m_lmf_app;
  bool running_server;
};

#endif
