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

/*
 * N2InfoNotifyApiImpl.h
 *
 *
 */

#ifndef NonUeN2InfoNotifyApiImpl_H_
#define NonUeN2InfoNotifyApiImpl_H_

#include <pistache/endpoint.h>
#include <pistache/http.h>
#include <pistache/router.h>
#include <memory>

#include <pistache/optional.h>

#include "NonUeN2InfoNotifyApi.h"
#include "ProblemDetails.h"
#include "lmf_app.hpp"

namespace oai::lmf::api {

class NonUeN2InfoNotifyApiImpl : public oai::lmf::api::NonUeN2InfoNotifyApi {
 public:
  NonUeN2InfoNotifyApiImpl(
      std::shared_ptr<Pistache::Rest::Router>,
      oai::lmf::app::lmf_app* lmf_app_inst);
  ~NonUeN2InfoNotifyApiImpl() {}

  void receive_non_ue_n2info_nrppa_notification(
      std::vector<mime_part>& parts, Pistache::Http::ResponseWriter& response);

 private:
  oai::lmf::app::lmf_app* m_lmf_app;
  // std::string m_address;
};

}  // namespace oai::lmf::api

#endif  // NonUeN2InfoNotifyApiImpl_H_
