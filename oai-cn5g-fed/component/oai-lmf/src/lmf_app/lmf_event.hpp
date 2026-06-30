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

#ifndef FILE_LMF_EVENT_HPP_SEEN
#define FILE_LMF_EVENT_HPP_SEEN

#include <boost/signals2.hpp>
namespace bs2 = boost::signals2;

#include "lmf.h"
#include "lmf_event_sig.hpp"
#include "task_manager.hpp"

namespace oai::lmf::app {
class task_manager;
class lmf_event {
 public:
  lmf_event(){};
  lmf_event(lmf_event const&) = delete;
  void operator=(lmf_event const&) = delete;

  static lmf_event& get_instance() {
    static lmf_event instance;
    return instance;
  }

  // class register/handle event
  friend class lmf_app;
  friend class lmf_nrf;
  friend class task_manager;

  //------------------------------------------------------------------------------
  /*
   * Subscribe to the task tick event
   * @param [const task_sig_t::slot_type &] sig
   * @param [uint64_t] period: interval between two events
   * @param [uint64_t] start:
   * @return void
   */
  bs2::connection subscribe_task_nf_heartbeat(
      const task_sig_t::slot_type& sig, uint64_t period, uint64_t start = 0);

 private:
  task_sig_t task_tick;
};
}  // namespace oai::lmf::app
#endif
