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

#ifndef FILE_LMF_GNB_SEEN
#define FILE_LMF_GNB_SEEN

#include "lmf_trp.hpp"

#include "GlobalRanNodeId.h"

#include "TRP-ID.h"

namespace oai::lmf::app {
using GnbId = uint64_t;

class Gnb {
 public:
  Gnb(GnbId const& id, oai::model::common::GlobalRanNodeId const& ncgi)
      : id{id}, ncgi{ncgi} {}
  const GnbId id;
  const oai::model::common::GlobalRanNodeId ncgi;
  std::map<TRP_ID_t, Trp> trp;
};

}  // namespace oai::lmf::app

#endif  // FILE_LMF_GNB_SEEN
