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
 * N2InfoNotifyApi.h
 *
 *
 */

#ifndef N2InfoNotifyApi_H_
#define N2InfoNotifyApi_H_

#include <pistache/http.h>
#include <pistache/router.h>

#include "mime_parser.hpp"

namespace oai::lmf::api {

class N2InfoNotifyApi {
 public:
  N2InfoNotifyApi(std::shared_ptr<Pistache::Rest::Router>);
  virtual ~N2InfoNotifyApi() {}
  void init();

 private:
  void setupRoutes();

  void notify_n2info_nrppa_handler(
      const Pistache::Rest::Request& request,
      Pistache::Http::ResponseWriter response);
  void notify_n2info_default_handler(
      const Pistache::Rest::Request& request,
      Pistache::Http::ResponseWriter response);

  std::shared_ptr<Pistache::Rest::Router> router;

  virtual void receive_n2info_nrppa_notification(
      const std::string& ueContextId, std::vector<mime_part>& parts,
      Pistache::Http::ResponseWriter& response) = 0;
};

}  // namespace oai::lmf::api

#endif /* N2InfoNotifyApi_H_ */
