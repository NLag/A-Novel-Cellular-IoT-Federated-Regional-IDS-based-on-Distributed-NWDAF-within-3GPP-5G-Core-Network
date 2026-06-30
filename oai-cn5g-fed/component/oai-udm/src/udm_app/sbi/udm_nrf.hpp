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

#ifndef FILE_UDM_NRF_SEEN
#define FILE_UDM_NRF_SEEN

#include <map>
#include <thread>

#include "logger.hpp"
#include "udm_config.hpp"
#include "udm_event.hpp"
#include "udm_profile.hpp"

namespace oai::udm::app {

class udm_nrf {
 public:
  // timer_id_t timer_udm_heartbeat;

  udm_nrf(udm_event& ev);
  udm_nrf(udm_nrf const&) = delete;
  virtual ~udm_nrf();
  void operator=(udm_nrf const&) = delete;

  void generate_uuid();

  /*
   * Start event nf heartbeat procedure
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
   * Start event nrf registration retry
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
   * Stop event nrf registration retry
   * @param [void]
   * @return void
   */
  void stop_nrf_registration_retry();

  /*
   * Generate a UDM profile for this instance
   * @param [void]
   * @return void
   */
  void generate_udm_profile();

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

 private:
  udm_event& m_event_sub;
  bs2::connection task_connection;
  bs2::connection retry_nrf_registration_task_connection;
  udm_profile udm_nf_profile;   // UDM profile
  std::string udm_instance_id;  // UDM instance id
};
}  // namespace oai::udm::app
#endif /* FILE_UDM_NRF_SEEN */
