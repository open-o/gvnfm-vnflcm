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
import json
import logging
import traceback
from threading import Thread

from lcm.pub.database.models import NfInstModel, JobStatusModel, NfvoRegInfoModel, VmInstModel, VNFCInstModel, \
    NetworkInstModel, SubNetworkInstModel, VLInstModel, PortInstModel, CPInstModel, StorageInstModel, FlavourInstModel
from lcm.pub.exceptions import NFLCMException
from lcm.pub.msapi.nfvolcm import vnfd_rawdata_get, apply_grant_to_nfvo
from lcm.pub.utils.jobutil import JobUtil
from lcm.pub.utils.timeutil import now_time
from lcm.pub.utils.values import ignore_case_get
from lcm.pub.vimapi import adaptor

logger = logging.getLogger(__name__)


class InstVnf(Thread):
    def __init__(self, data, nf_inst_id, job_id):
        super(InstVnf, self).__init__()
        self.data = data
        self.nf_inst_id = nf_inst_id
        self.job_id = job_id
        self.nfvo_inst_id = ''
        self.vnfm_inst_id = ''
        self.vnfd_info = []
        self.inst_resource = {'volumn':[],#'volumn':[{"vim_id": "1"}, {"res_id": "2"}]
                              'network':[],
                              'subnet':[],
                              'port':[],
                              'flavor':[],
                              'vm':[],
                              }
        self.create_res_result = {
            'jobid': 'res_001',
            'resourceResult': [{'name': 'vm01'}, {'name': 'vm02'}],
            'resource_result':{
                'affectedvnfc':[
                    {
                        'status':'success',
                        'vnfcinstanceid':'1',
                        'computeresource':{'resourceid':'11'},
                        'vduid':'111',
                        'vdutype':'1111'
                    }
                ],
                'affectedvirtuallink':[
                    {
                        'status': 'success',
                        'virtuallinkinstanceid':'',
                        'networkresource':{'resourceid':'1'},
                        'subnetworkresource':{'resourceid':'1'},
                        'virtuallinkdescid': '',
                    }
                ],
                'affectedcp':[{
                    'status': 'success',
                    'portresource':{'resourceid':'1'},
                    'cpinstanceid':'2',
                    'cpdid':'22',
                    'ownertype':'222',
                    'ownerid':'2222',
                    'virtuallinkinstanceid':'22222',

                }],

            }
        }

    def run(self):
        try:
            self.inst_pre()
            self.apply_grant()
            self.create_res()
            self.check_res_status()
            # self.wait_inst_finish(args)
            # self.lcm_notify(args)
            JobUtil.add_job_status(self.job_id, 100, "Instantiate Vnf success.")
            is_exist = JobStatusModel.objects.filter(jobid=self.job_id).exists()
            logger.debug("check_ns_inst_name_exist::is_exist=%s" % is_exist)
        except NFLCMException as e:
            self.vnf_inst_failed_handle(e.message)
            # self.rollback(e.message)
        except:
            self.vnf_inst_failed_handle('unexpected exception')
            logger.error(traceback.format_exc())
            # self.rollback('unexpected exception')

    def inst_pre(self):
        vnf_insts = NfInstModel.objects.filter(nfinstid=self.nf_inst_id)
        if not vnf_insts.exists():
            raise NFLCMException('VNF nf_inst_id is not exist.')

        self.vnfm_inst_id = vnf_insts[0].vnfm_inst_id
        if vnf_insts[0].instantiationState != 'NOT_INSTANTIATED':
            raise NFLCMException('VNF instantiationState is not NOT_INSTANTIATED.')

        #get rawdata by vnfd_id
        ret = vnfd_rawdata_get(vnf_insts[0].vnfdid)
        if ret[0] != 0:
            raise NFLCMException("Get vnfd_raw_data failed.")
        self.vnfd_info = json.JSONDecoder().decode(ret[1])
        #checkParameterExist
        for cp in self.data:
            if cp not in self.vnfd_info:
                raise NFLCMException('Input parameter is not defined in vnfd_info.')
        #get nfvo info
        JobUtil.add_job_status(self.job_id, 5, 'GET_NFVO_CONNECTION_INFO')
        self.load_nfvo_config()

        #update NfInstModel
        NfInstModel.objects.filter(nfinstid=self.nf_inst_id).update(flavour_id=ignore_case_get(self.data, "flavourId"),
                                                                    vnf_level=ignore_case_get(self.data, 'instantiationLevelId'),
                                                                    input_params=ignore_case_get(self.data, 'additionalParams'),
                                                                    extension=ignore_case_get(self.data, ''),
                                                                    initallocatedata=self.vnfd_info,
                                                                    localizationLanguage=ignore_case_get(self.data, 'localizationLanguage'),
                                                                    lastuptime=now_time())
        JobUtil.add_job_status(self.job_id, 10, 'Nf instancing pre-check finish')
        logger.info("Nf instancing pre-check finish")

    def apply_grant(self):
        logger.info('[NF instantiation] send resource grand request to nfvo start')
        #self.check_vm_capacity()
        content_args = {'nfvoInstanceId': self.nfvo_inst_id, 'vnfmInstanceId': self.vnfm_inst_id,
                        'nfInstanceId': self.nf_inst_id, 'nfDescriptorId': '',
                        'lifecycleOperation': 'Instantiate', 'jobId': self.job_id, 'addResource': [],
                        'removeResource': [], 'placementConstraint': [], 'exVimIdList': [], 'additionalParam': {}}

        vdus = self.vnfd_info['vdus']
        res_index = 1
        for vdu in vdus:
            res_def = {'type': 'VDU', 'resourceDefinitionId': str(res_index), 'vduId': vdu['vdu_id'],
                       'vimid': '', 'tenant': ''}
            if self.vnfd_info['metadata']['cross_dc']:
                res_def['vimid'] = vdu['properties']['location_info']['vimId']
                res_def['tenant'] = vdu['properties']['location_info']['tenant']
            content_args['addResource'].append(res_def)
            res_index += 1
        logger.info('content_args=%s' % content_args)
        resp = apply_grant_to_nfvo(content_args)
        logger.info("[NF instantiation] get grant response = %s" % resp)
        if resp[0] != 0:
            raise NFLCMException('Nf instancing apply grant exception')

        #update_resources_table()
        NfInstModel.objects.filter(nfinstid=self.nf_inst_id).update(instantiationState='INSTANTIATED', lastuptime=now_time())
        JobUtil.add_job_status(self.job_id, 20, 'Nf instancing apply grant finish')
        logger.info("Nf instancing apply grant finish")

    def create_res(self):
        logger.info("[NF instantiation] create resource start")
        adaptor.create_vim_res(self.vnfd_info, self.do_notify, self.do_rollback)

        JobUtil.add_job_status(self.job_id, 70, '[NF instantiation] create resource finish')
        logger.info("[NF instantiation] create resource finish")

    def check_res_status(self):
        logger.info("[NF instantiation] confirm all vms are active start")
        vnfcs = self.create_res_result['resource_result']['affectedvnfc']
        for vnfc in vnfcs:
            if 'success' != vnfc['status']:
                logger.error("VNFC_STATUS_IS_NOT_ACTIVE[vduid=%s]" % vnfc['vduId'])
                raise NFLCMException(msgid="VNFC_STATUS_IS_NOT_ACTIVE[vduid=%s]", args=vnfc['vduId'])

        JobUtil.add_job_status(self.job_id, 80, 'SAVE_VNFC_TO_DB')
        vls = self.create_res_result['resource_result']['affectedvirtuallink']
        cps = self.create_res_result['resource_result']['affectedcp']

        for vnfc in vnfcs:
            if 'failed' == vnfc['status']:
                continue
            compute_resource = vnfc['computeresource']
            vminst = VmInstModel.objects.filter(resouceid=compute_resource['resourceid']).first()
            VNFCInstModel.objects.create(
                vnfcinstanceid=vnfc['vnfcinstanceid'],
                vduid=vnfc['vduid'],
                vdutype=vnfc['vdutype'],
                nfinstid=self.nf_inst_id,
                vmid=vminst.vmid)
        for vl in vls:
            if 'failed' == vl['status']:
                continue
            network_resource = vl['networkresource']
            subnet_resource = vl['subnetworkresource']
            networkinst = NetworkInstModel.objects.filter(resouceid=network_resource['resourceid']).first()
            subnetinst = SubNetworkInstModel.objects.filter(resouceid=subnet_resource['resourceid']).first()
            VLInstModel.objects.create(
                vlinstanceid=vl['virtuallinkinstanceid'],
                vldid=vl['virtuallinkdescid'],
                ownertype='0',
                ownerid=self.nf_inst_id,
                relatednetworkid=networkinst.networkid,
                relatedsubnetworkid=subnetinst.subnetworkid)
        # # for vs in vss:
        for cp in cps:
            if 'failed' == cp['status']:
                continue
            port_resource = cp['portresource']
            portinst = PortInstModel.objects.filter(resouceid=port_resource['resourceid']).first()
            ttt = portinst.portid
            CPInstModel.objects.create(
                cpinstanceid=cp['cpinstanceid'],
                cpdid=cp['cpdid'],
                relatedtype='2',
                relatedport=portinst.portid,
                ownertype=cp['ownertype'],
                ownerid=cp['ownerid'],
                vlinstanceid=cp['virtuallinkinstanceid'])
        # self.add_job(43, 'INST_DPLY_VM_PRGS')
        logger.info("[NF instantiation] confirm all vms are active end")

    # def wait_inst_finish(self, args):
    #     try:
    #         logger.info('wait_inst_finish, args=%s' % args)
    #         # WaitInstFinishTask(args).do_biz()
    #         return {'result': '100', 'msg': 'Nf instancing wait finish', 'context': {}}
    #     except Exception as e:
    #         logger.error('Nf instancing wait exception=%s' % e.message)
    #         logger.error(traceback.format_exc())
    #         return {'result': '255', 'msg': 'Nf instancing wait exception', 'context': {}}

    def lcm_notify(self, args):
        logger.info('lcm_notify, args=%s' % args)
        # LcmNotifyTask(args).do_biz()
        return {'result': '100', 'msg': 'Nf instancing lcm notify finish', 'context': {}}

    # def rollback(self, args):
    #     try:
    #         logger.info('inst_exception, args=%s' % args)
    #         # InstExceptionTask(args).do_biz()
    #         return {'result': '100', 'msg': 'Nf instancing exception process finish', 'context': {}}
    #     except Exception as e:
    #         logger.error('Nf instancing exception process exception=%s' % e.message)
    #         logger.error(traceback.format_exc())
    #         return {'result': '255', 'msg': 'Nf instancing exception process exception', 'context': {}}

    def load_nfvo_config(self):
        logger.info("[NF instantiation]get nfvo connection info start")
        reg_info = NfvoRegInfoModel.objects.filter(vnfminstid='vnfm111').first()
        if reg_info:
            self.nfvo_inst_id = reg_info.nfvoid
            logger.info("[NF instantiation] Registered nfvo id is [%s]"%self.nfvo_inst_id)
        else:
            raise NFLCMException("Nfvo was not registered")
        logger.info("[NF instantiation]get nfvo connection info end")

    def vnf_inst_failed_handle(self, error_msg):
        logger.error('VNF instantiation failed, detail message: %s' % error_msg)
        NfInstModel.objects.filter(nfinstid=self.nf_inst_id).update(status='failed', lastuptime=now_time())
        JobUtil.add_job_status(self.job_id, 255, error_msg)

    def do_notify(self, res_type, progress, ret):
        logger.info('creating [%s] resource'%res_type)
        progress = 20 + int(progress/2)     #20-70
        if res_type == adaptor.RES_VOLUME:
            logger.info('Create vloumns!')
            if ret["returnCode"] == adaptor.RES_NEW:#new create
                self.inst_resource['volumn'].append({"vim_id": ignore_case_get(ret, "vim_id")}, {"res_id": ignore_case_get(ret, "res_id")})
            JobUtil.add_job_status(self.job_id, progress, 'Create vloumns!')
            StorageInstModel.objects.create(
                storageid='1',
                vimid='1',
                resouceid='1',
                name='40G',
                tenant='admin',
                insttype=0,
                instid=self.nf_inst_id)
        elif res_type == adaptor.RES_NETWORK:
            logger.info('Create networks!')
            if ret["returnCode"] == adaptor.RES_NEW:
                self.inst_resource['network'].append({"vim_id": ignore_case_get(ret, "vim_id")}, {"res_id": ignore_case_get(ret, "res_id")})
            # self.inst_resource['network'].append({"vim_id": "1"}, {"res_id": "2"})
            JobUtil.add_job_status(self.job_id, progress, 'Create networks!')
            NetworkInstModel.objects.create(
                networkid='1',
                vimid='1',
                resouceid='1',
                name='pnet_network',
                tenant='admin',
                insttype=0,
                instid=self.nf_inst_id)
        elif res_type == adaptor.RES_SUBNET:
            logger.info('Create subnets!')
            if ret["returnCode"] == adaptor.RES_NEW:
                self.inst_resource['subnet'].append({"vim_id": ignore_case_get(ret, "vim_id")}, {"res_id": ignore_case_get(ret, "res_id")})
            # self.inst_resource['subnet'].append({"vim_id": "1"}, {"res_id": "2"})
            JobUtil.add_job_status(self.job_id, progress, 'Create subnets!')
            SubNetworkInstModel.objects.create(
                subnetworkid='1',
                vimid='1',
                resouceid='1',
                networkid='1',
                name='sub_pnet',
                tenant='admin',
                insttype=0,
                instid=self.nf_inst_id)
        elif res_type == adaptor.RES_PORT:
            logger.info('Create ports!')
            if ret["returnCode"] == adaptor.RES_NEW:
                self.inst_resource['port'].append({"vim_id": ignore_case_get(ret, "vim_id")}, {"res_id": ignore_case_get(ret, "res_id")})
            # self.inst_resource['port'].append({"vim_id": "1"}, {"res_id": "2"})
            JobUtil.add_job_status(self.job_id, progress, 'Create ports!')
            PortInstModel.objects.create(
                portid='1',
                networkid='1',
                subnetworkid='1',
                vimid='1',
                resouceid='1',
                name='aaa_pnet_cp',
                tenant='admin',
                insttype=0,
                instid=self.nf_inst_id)
        elif res_type == adaptor.RES_FLAVOR:
            logger.info('Create flavors!')
            if ret["returnCode"] == adaptor.RES_NEW:
                self.inst_resource['flavor'].append({"vim_id": ignore_case_get(ret, "vim_id")}, {"res_id": ignore_case_get(ret, "res_id")})
            # self.inst_resource['flavor'].append({"vim_id": "1"}, {"res_id": "2"})
            JobUtil.add_job_status(self.job_id, progress, 'Create flavors!')
            FlavourInstModel.objects.create(
                falavourid='1',
                name='1',
                vcpu='1',
                extraspecs='1',
                instid=self.nf_inst_id)
        elif res_type == adaptor.RES_VM:
            logger.info('Create vms!')
            if ret["returnCode"] == adaptor.RES_NEW:
                self.inst_resource['vm'].append({"vim_id": ignore_case_get(ret, "vim_id")}, {"res_id": ignore_case_get(ret, "res_id")})
            # self.inst_resource['vm'].append({"vim_id": "1"}, {"res_id": "2"})
            JobUtil.add_job_status(self.job_id, progress, 'Create vms!')
            VmInstModel.objects.create(
                vmid="1",
                vimid="1",
                resouceid="11",
                insttype=0,
                instid=self.nf_inst_id,
                vmname="test_01",
                operationalstate=1)

    def do_rollback(self, args_=None):
        logger.error('error info : %s'%(args_))
        adaptor.delete_vim_res(self.inst_resource, self.do_notify_delete)
        logger.error('rollback resource complete')

        StorageInstModel.objects.filter(instid=self.nf_inst_id).delete()
        NetworkInstModel.objects.filter(instid=self.nf_inst_id).delete()
        SubNetworkInstModel.objects.filter(instid=self.nf_inst_id).delete()
        PortInstModel.objects.filter(instid=self.nf_inst_id).delete()
        FlavourInstModel.objects.filter(instid=self.nf_inst_id).delete()
        VmInstModel.objects.filter(instid=self.nf_inst_id).delete()
        logger.error('delete table complete')
        raise NFLCMException("Create resource failed")

    def do_notify_delete(ret):
        logger.error('Deleting [%s] resource'%ret)


