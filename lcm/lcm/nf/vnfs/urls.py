# Copyright 2017 ZTE Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from django.conf.urls import patterns, url
from rest_framework.urlpatterns import format_suffix_patterns

from lcm.nf.vnfs.views import CreateVnfIdentifier, InstantiateVnf, DeleteVnfIdentifier, QueryMultipleVnf, TerminateVnf, \
    QuerySingleVnf, GetOperationStatus

urlpatterns = patterns('',
                       url(r'^gvnfmapi/lcm/v1/vnf_instances$', CreateVnfIdentifier.as_view()),
                       url(r'^gvnfmapi/lcm/v1/vnf_instances/(?P<instanceId>[0-9a-zA-Z_-]+)/instantiate$', InstantiateVnf.as_view()),
                       url(r'^gvnfmapi/lcm/v1/vnf_instances/(?P<instanceId>[0-9a-zA-Z_-]+)$',
                           DeleteVnfIdentifier.as_view()),
                       url(r'^gvnfmapi/lcm/v1/vnf_instances/(?P<instanceId>[0-9a-zA-Z_-]+)/terminate$',
                           TerminateVnf.as_view()),
                       url(r'^gvnfmapi/lcm/v1/vnf_instances$', QueryMultipleVnf.as_view()),
                       url(r'^gvnfmapi/lcm/v1/vnf_instances/(?P<instanceId>[0-9a-zA-Z_-]+)$', QuerySingleVnf.as_view()),
                       url(
                           r'^gvnfmapi/lcm/v1/vnf_lc_ops/(?P<vnfLcOpId>[0-9a-zA-Z_-]+)&responseId=(?P<responseId>[0-9a-zA-Z_-]+)$',
                           GetOperationStatus.as_view()),
                       )

urlpatterns = format_suffix_patterns(urlpatterns)