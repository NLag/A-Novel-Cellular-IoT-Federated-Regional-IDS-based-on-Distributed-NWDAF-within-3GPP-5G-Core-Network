################################################################################
# Licensed to the OpenAirInterface (OAI) Software Alliance under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The OpenAirInterface Software Alliance licenses this file to You under
# the OAI Public License, Version 1.1  (the "License"); you may not use this file
# except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.openairinterface.org/?page_id=698
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#-------------------------------------------------------------------------------
# For more information about the OpenAirInterface (OAI) Software Alliance:
#      contact@openairinterface.org
################################################################################

include_directories(${SRC_TOP_DIR}/api_server/api)
include_directories(${SRC_TOP_DIR}/api_server/impl)
include_directories(${SRC_TOP_DIR}/api_server/)
include_directories(${SRC_TOP_DIR}/common/)
#include_directories(${SRC_TOP_DIR}/lpp)
include_directories(${SRC_TOP_DIR}/nrppa)
include_directories(${SRC_TOP_DIR}/${MOUNTED_COMMON}/common)
include_directories(${SRC_TOP_DIR}/${MOUNTED_COMMON}/config)
include_directories(${SRC_TOP_DIR}/${MOUNTED_COMMON}/http)
include_directories(${SRC_TOP_DIR}/${MOUNTED_COMMON}/logger)
include_directories(${SRC_TOP_DIR}/${MOUNTED_COMMON}/model/common_model)
include_directories(${SRC_TOP_DIR}/${MOUNTED_COMMON}/model/lmf)
include_directories(${SRC_TOP_DIR}/${MOUNTED_COMMON}/utils)
include_directories(${SRC_TOP_DIR}/${MOUNTED_COMMON}/utils/bstr)

include(${SRC_TOP_DIR}/${MOUNTED_COMMON}/http/http.cmake)
include(${SRC_TOP_DIR}/${MOUNTED_COMMON}/logger/logger.cmake)
include(${SRC_TOP_DIR}/${MOUNTED_COMMON}/model/lmf/lmf.cmake)
include(${SRC_TOP_DIR}/${MOUNTED_COMMON}/utils/utils.cmake)

file(GLOB LMF_src_files
  lmf_app.cpp
  lmf_config.cpp
  lmf_config_yaml.cpp 
  task_manager.cpp
  lmf_event.cpp
  lmf_profile.cpp
  lmf_nrf.cpp 
  lmf_location_determination.cpp
  lmf_n1_n2_message_subscription.cpp
  lmf_non_ue_n2_message_subscription.cpp
)


add_library (LMF STATIC
  ${LMF_src_files}
)
#target_link_libraries(LMF LPP NRPPA)
target_link_libraries(LMF NRPPA)
