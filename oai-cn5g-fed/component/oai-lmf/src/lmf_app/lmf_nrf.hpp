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

#ifndef FILE_LMF_NRF_SEEN
#define FILE_LMF_NRF_SEEN

#include "lmf_event.hpp"
#include "lmf_profile.hpp"

namespace oai::lmf::app {

class lmf_nrf {
 private:
 public:
  lmf_profile lmf_nf_profile;   // LMF profile
  std::string lmf_instance_id;  // LMF instance id
  // timer_id_t timer_lmf_heartbeat;

  lmf_nrf(lmf_event& ev);
  lmf_nrf(lmf_nrf const&) = delete;
  virtual ~lmf_nrf();
  void operator=(lmf_nrf const&) = delete;

  void generate_uuid();

  /*
   * Start event NF heartbeat procedure
   * @param [void]
   * @return void
   */
  void start_event_nf_heartbeat(std::string& remoteURI);

  /*
   * Trigger NF heartbeat procedure
   * @param [void]
   * @return void
   */
  void trigger_nf_heartbeat_procedure(uint64_t ms);

  /*
   * Start event NRF registration retry
   * @param [void]
   * @return void
   */
  void start_nrf_registration_retry();

  /*
   * Trigger NF registration procedure
   * @param [void]
   * @return void
   */
  void trigger_nrf_registration_retry_procedure(uint64_t ms);

  /*
   * Stop event NRF registration retry
   * @param [void]
   * @return void
   */
  void stop_nrf_registration_retry();

  /*
   * Trigger NF instance registration to NRF
   * @param [void]
   * @return void
   */
  void register_to_nrf();

  /*
   * Trigger NF instance deregistration to NRF
   * @param [void]
   * @return void
   */
  void deregister_to_nrf();

  /*
   * Generate a LMF profile for this instance
   * @param [void]
   * @return void
   */
  void generate_lmf_profile(
      lmf_profile& lmf_nf_profile, std::string& lmf_instance_id);

 private:
  lmf_event& m_event_sub;
  bs2::connection task_connection;
  bs2::connection retry_nrf_registration_task_connection;
};

}  // namespace oai::lmf::app

extern oai::lmf::app::lmf_nrf* lmf_nrf_inst;

#endif /* FILE_LMF_NRF_SEEN */
