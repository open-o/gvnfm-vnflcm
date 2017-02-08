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
from django.db import models


class VnfInstModel(models.Model):
    class Meta:
        db_table = 'GVNFM_VNFINST'

    id = models.CharField(db_column='ID', primary_key=True, max_length=200)
    name = models.CharField(db_column='NAME', max_length=200)
    vnfd_id = models.CharField(db_column='VNFDID', max_length=200)
    description = models.CharField(db_column='DESCRIPTION', max_length=255, null=True, blank=True)
    status = models.CharField(db_column='STATUS', max_length=200, null=True, blank=True)
    create_time = models.CharField(db_column='CREATETIME', max_length=200, null=True, blank=True)
    lastuptime = models.CharField(db_column='LASTUPTIME', max_length=200, null=True, blank=True)


