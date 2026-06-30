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

#ifndef FILE_N1_N2_MESSAGE_SUBSCRIPTION_SEEN
#define FILE_N1_N2_MESSAGE_SUBSCRIPTION_SEEN

#include <string>
#include <memory>

#include <boost/core/noncopyable.hpp>

namespace oai::lmf::app {

class N1N2MessageSubscription : private boost::noncopyable {
 public:
  const std::string id, supi;

  N1N2MessageSubscription(const std::string& supi)
      : id{N1N2MessageSubscription::subscribe(supi)}, supi{supi} {}

  ~N1N2MessageSubscription() {
    N1N2MessageSubscription::unsubscribe(this->id, this->supi);
  }

  static std::string subscribe(std::string const& supi);
  static void unsubscribe(std::string const& id, std::string const& supi);
};

}  // namespace oai::lmf::app

#endif  // ifndef FILE_N1_N2_MESSAGE_SUBSCRIPTION_SEEN