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

import logging
import sys
import time
import traceback

from lcm.pub.utils.values import ignore_case_get, set_opt_val
from . import api
from .exceptions import VimException

logger = logging.getLogger(__name__)

ERR_CODE = "500"
RES_EXIST, RES_NEW = 0, 1
IP_V4, IP_V6 = 4, 6
BOOT_FROM_VOLUME, BOOT_FROM_IMAGE = 1, 2

RES_VOLUME = "volume"
RES_NETWORK = "network"
RES_SUBNET = "subnet"
RES_PORT = "port"
RES_FLAVOR = "flavor"
RES_VM = "vm"


def get_tenant_id(vim_cache, vim_id, tenant_name):
    if vim_id not in vim_cache:
        tenants = api.list_tenant(vim_id)
        vim_cache[vim_id] = {}
        for tenant in tenants["tenants"]:
            id, name = tenant["id"], tenant["name"]
            vim_cache[vim_id][name] = id
    if tenant_name not in vim_cache[vim_id]:
        raise VimException("Tenant(%s) not found in vim(%s)" % (tenant_name, vim_id), ERR_CODE)
    return vim_cache[vim_id][tenant_name]

def set_res_cache(res_cache, res_type, key, val):
    if res_type not in res_cache:
        res_cache[res_type] = {}
    if key in res_cache[res_type]:
        raise VimException("Duplicate key(%s) of %s" % (key, res_type), ERR_CODE)
    res_cache[res_type][key] = val

def get_res_id(res_cache, res_type, key):
    if res_type not in res_cache:
        raise VimException("%s not found in cache" % res_type, ERR_CODE)
    if key not in res_cache[res_type]:
        raise VimException("%s(%s) not found in cache" % (res_type, key), ERR_CODE)
    return res_cache[res_type][key]

def create_vim_res(data, do_notify):
    vim_cache, res_cache = {}, {}
    for vol in ignore_case_get(data, "volume_storages"):
        create_volume(vim_cache, res_cache, vol, do_notify, RES_VOLUME)
    for network in ignore_case_get(data, "vls"):
        create_network(vim_cache, res_cache, network, do_notify, RES_NETWORK)
    for subnet in ignore_case_get(data, "vls"):
        create_subnet(vim_cache, res_cache, subnet, do_notify, RES_SUBNET)
    for port in ignore_case_get(data, "cps"):
        create_port(vim_cache, res_cache, data, port, do_notify, RES_PORT)
    for flavor in ignore_case_get(data, "vdus"):
        create_flavor(vim_cache, res_cache, data, flavor, do_notify, RES_FLAVOR)
    for vm in ignore_case_get(data, "vdus"):
        create_vm(vim_cache, res_cache, data, vm, do_notify, RES_VM)

def delete_vim_res(data, do_notify):
    res_types = [RES_VM, RES_FLAVOR, RES_PORT, RES_SUBNET, RES_NETWORK, RES_VOLUME]
    res_del_funs = [api.delete_vm, api.delete_flavor, api.delete_port, 
        api.delete_subnet, api.delete_network, api.delete_volume]
    for res_type, res_del_fun in zip(res_types, res_del_funs):
        for res in ignore_case_get(data, res_type):
            try:
                if 1 == res["is_predefined"]:
                    res_del_fun(res["vim_id"], res["tenant_id"], res["res_id"])
            except VimException as e:
                logger.error("Failed to delete %s(%s)", res_type, res["res_id"])
                logger.error("%s:%s", e.http_code, e.message)
            do_notify(res_type, res["res_id"])

def create_volume(vim_cache, res_cache, vol, do_notify, res_type):
    location_info = vol["properties"]["location_info"]
    param = {
        "name": vol["properties"]["volume_name"],
        "volumeSize": int(ignore_case_get(vol["properties"], "size", "0").replace('GB', '').strip())
    }
    set_opt_val(param, "imageName", ignore_case_get(vol, "image_file"))
    set_opt_val(param, "volumeType", ignore_case_get(vol["properties"], "custom_volume_type"))
    set_opt_val(param, "availabilityZone", ignore_case_get(location_info, "availability_zone"))
    vim_id, tenant_name = location_info["vimid"], location_info["tenant"]
    tenant_id = get_tenant_id(vim_cache, vim_id, tenant_name)
    ret = api.create_volume(vim_id, tenant_id, param)
    ret["nodeId"] = vol["volume_storage_id"]
    do_notify(res_type, ret)
    vol_id, vol_name, return_code = ret["id"], ret["name"], ret["returnCode"]
    set_res_cache(res_cache, res_type, vol["volume_storage_id"], vol_id)
    retry_count, max_retry_count = 0, 300
    while retry_count < max_retry_count:
        vol_info = api.get_volume(vim_id, tenant_id, vol_id)
        if vol_info["status"].upper() == "AVAILABLE":
            logger.debug("Volume(%s) is available", vol_id)
            return
        time.sleep(2)
        retry_count = retry_count + 1
    raise VimException("Failed to create Volume(%s): Timeout." % vol_name, ERR_CODE)
    
def create_network(vim_cache, res_cache, network, do_notify, res_type):
    location_info = network["properties"]["location_info"]
    param = {
        "name": network["properties"]["network_name"],
        "shared": False,
        "networkType": network["properties"]["network_type"],
        "physicalNetwork": ignore_case_get(network["properties"], "physical_network")
    }
    set_opt_val(param, "vlanTransparent", ignore_case_get(network["properties"], "vlan_transparent"))
    set_opt_val(param, "segmentationId", int(ignore_case_get(network["properties"], "segmentation_id", "0")))
    set_opt_val(param, "routerExternal", ignore_case_get(network, "route_external"))
    vim_id, tenant_name = location_info["vimid"], location_info["tenant"]
    tenant_id = get_tenant_id(vim_cache, vim_id, tenant_name)
    ret = api.create_network(vim_id, tenant_id, param)
    ret["nodeId"] = network["vl_id"]
    do_notify(res_type, ret)
    set_res_cache(res_cache, res_type, network["vl_id"], ret["id"])
    
def create_subnet(vim_cache, res_cache, subnet, do_notify, res_type):
    location_info = subnet["properties"]["location_info"]
    network_id = get_res_id(res_cache, RES_NETWORK, subnet["vl_id"])
    param = {
        "networkId": network_id,
        "name": subnet["properties"]["name"],
        "cidr": ignore_case_get(subnet["properties"], "cidr"),
        "ipVersion": ignore_case_get(subnet["properties"], "ip_version", IP_V4)
    }
    set_opt_val(param, "enableDhcp", ignore_case_get(subnet["properties"], "dhcp_enabled"))
    set_opt_val(param, "gatewayIp", ignore_case_get(subnet["properties"], "gateway_ip"))
    set_opt_val(param, "dnsNameservers", ignore_case_get(subnet["properties"], "dns_nameservers"))
    allocation_pool = {}
    set_opt_val(allocation_pool, "start", ignore_case_get(subnet["properties"], "start_ip"))
    set_opt_val(allocation_pool, "end", ignore_case_get(subnet["properties"], "end_ip"))
    if allocation_pool:
        param["allocationPools"] = [allocation_pool]
    set_opt_val(param, "hostRoutes", ignore_case_get(subnet["properties"], "host_routes"))
    vim_id, tenant_name = location_info["vimid"], location_info["tenant"]
    tenant_id = get_tenant_id(vim_cache, vim_id, tenant_name)
    ret = api.create_subnet(vim_id, tenant_id, param)
    do_notify(res_type, ret)
    set_res_cache(res_cache, res_type, subnet["vl_id"], ret["id"])
    
def create_port(vim_cache, res_cache, data, port, do_notify, res_type):
    location_info = None
    port_ref_vdu_id = ignore_case_get(port, "vdu_id")
    for vdu in ignore_case_get(data, "vdus"):
        if vdu["vdu_id"] == port_ref_vdu_id:
            location_info = vdu["properties"]["location_info"]
            if port["cp_id"] not in vdu["cps"]:
                vdu["cps"].append(port["cp_id"])
            break
    if not location_info:
        err_msg = "vdu_id(%s) for cp(%s) is not defined"
        raise VimException(err_msg % (port_ref_vdu_id, port["cp_id"]), ERR_CODE)
    network_id = ignore_case_get(port, "networkId")
    subnet_id = ignore_case_get(port, "subnetId")
    if not network_id:
        network_id = get_res_id(res_cache, RES_NETWORK, port["vl_id"])
        subnet_id = get_res_id(res_cache, RES_SUBNET, port["vl_id"])
    param = {
        "networkId": network_id,
        "name": port["properties"].get("name","undefined")
    }
    set_opt_val(param, "subnetId", subnet_id)
    set_opt_val(param, "macAddress", ignore_case_get(port["properties"], "mac_address"))
    set_opt_val(param, "ip", ignore_case_get(port["properties"], "ip_address"))
    set_opt_val(param, "vnicType", ignore_case_get(port["properties"], "vnic_type"))
    set_opt_val(param, "securityGroups", "") # TODO
    vim_id, tenant_name = location_info["vimid"], location_info["tenant"]
    tenant_id = get_tenant_id(vim_cache, vim_id, tenant_name)
    ret = api.create_port(vim_id, tenant_id, param)
    ret["nodeId"] = port["cp_id"]
    do_notify(res_type, ret)
    set_res_cache(res_cache, res_type, port["cp_id"], ret["id"])

def create_flavor(vim_cache, res_cache, data, flavor, do_notify, res_type):
    location_info = flavor["properties"]["location_info"]
    local_storages = ignore_case_get(data, "local_storages")
    param = {
        "name": "Flavor_%s" % flavor["vdu_id"],
        "vcpu": int(flavor["nfv_compute"]["num_cpus"]),
        "memory": int(flavor["nfv_compute"]["mem_size"].replace('GB', '').strip()),
        "isPublic": True
    }
    for local_storage_id in ignore_case_get(flavor, "local_storages"):
        for local_storage in local_storages:
            if local_storage_id != local_storage["local_storage_id"]:
                continue
            disk_type = local_storage["properties"]["disk_type"]
            disk_size = int(local_storage["properties"]["size"].replace('GB', '').strip())
            if disk_type == "root":
                param["disk"] = disk_size
            elif disk_type == "ephemeral":
                param["ephemeral"] = disk_size
            elif disk_type == "swap":
                param["swap"] = disk_size
    flavor_extra_specs = ignore_case_get(flavor["nfv_compute"], "flavor_extra_specs")
    extra_specs = []
    for es in flavor_extra_specs:
        extra_specs.append({"keyName": es, "value": flavor_extra_specs[es]})
    set_opt_val(param, "extraSpecs", extra_specs)
    vim_id, tenant_name = location_info["vimid"], location_info["tenant"]
    tenant_id = get_tenant_id(vim_cache, vim_id, tenant_name)
    ret = api.create_flavor(vim_id, tenant_id, param)
    do_notify(res_type, ret)
    set_res_cache(res_cache, res_type, flavor["vdu_id"], ret["id"])
    
def create_vm(vim_cache, res_cache, data, vm, do_notify, res_type):
    location_info = vm["properties"]["location_info"]
    vim_id, tenant_name = location_info["vimid"], location_info["tenant"]
    tenant_id = get_tenant_id(vim_cache, vim_id, tenant_name)
    param = {
        "name": vm["properties"].get("name","undefined"),
        "flavorId": get_res_id(res_cache, RES_FLAVOR, vm["vdu_id"]),
        "boot": {},
        "nicArray": [],
        "contextArray": [],
        "volumeArray": []
    }
    # set boot param
    if "image_file" in vm and vm["image_file"]:
        param["boot"]["type"] = BOOT_FROM_IMAGE
        img_name = ""
        for img in ignore_case_get(data, "image_files"):
            if vm["image_file"] == img["image_file_id"]:
               img_name = img["properties"]["name"]
               break
        if not img_name:
            raise VimException("Undefined image(%s)" % vm["image_file"], ERR_CODE)
        images = api.list_image(vim_id, tenant_id)
        for image in images["images"]:
            if img_name == image["name"]:
                param["boot"]["imageId"] = image["id"]
                break
        if "imageId" not in param["boot"]:
            raise VimException("Image(%s) not found in Vim(%s)" % (img_name, vim_id), ERR_CODE)
    elif vm["volume_storages"]:
        param["boot"]["type"] = BOOT_FROM_VOLUME
        vol_id = vm["volume_storages"][0]["volume_storage_id"]
        param["boot"]["volumeId"] = get_res_id(res_cache, RES_VOLUME, vol_id)
    else:
        raise VimException("No image and volume defined", ERR_CODE)

    for cp_id in ignore_case_get(vm, "cps"):
        param["nicArray"].append({
            "portId": get_res_id(res_cache, RES_PORT, cp_id)
        })
    for inject_data in ignore_case_get(vm["properties"], "inject_data_list"):
        param["contextArray"].append({
            "fileName": inject_data["file_name"],
            "fileData": inject_data["file_data"]
        })
    for vol_data in ignore_case_get(vm, "volume_storages"):
        vol_id = vol_data["volume_storage_id"]
        param["volumeArray"].append({
            "volumeId": get_res_id(res_cache, RES_VOLUME, vol_id)
        })

    set_opt_val(param, "availabilityZone", ignore_case_get(location_info, "availability_zone"))
    set_opt_val(param, "userdata", "") # TODO Configuration information or scripts to use upon launch
    set_opt_val(param, "metadata", "") # TODO [{"keyName": "foo", "value": "foo value"}]
    set_opt_val(param, "securityGroups", "") # TODO List of names of security group
    set_opt_val(param, "serverGroup", "") # TODO the ServerGroup for anti-affinity and affinity
    
    ret = api.create_vm(vim_id, tenant_id, param)
    do_notify(res_type, ret)
    #vm_id, vm_name, return_code = ret["id"], ret["name"], ret["returnCode"]
    vm_id, return_code = ret["id"], ret["returnCode"]
    if ignore_case_get(ret, "name"):
        vm_name = vm["properties"].get("name", "undefined")
        logger.debug("vm_name:%s" % vm_name)
    opt_vm_status = "Timeout"
    retry_count, max_retry_count = 0, 100
    while retry_count < max_retry_count:
        vm_info = api.get_vm(vim_id, tenant_id, vm_id)
        if vm_info["status"].upper() == "ACTIVE":
            logger.debug("Vm(%s) is active", vim_id)
            return
        if vm_info["status"].upper() == "ERROR":
            opt_vm_status = vm_info["status"]
            break
        time.sleep(2)
        retry_count = retry_count + 1
    raise VimException("Failed to create Vm(%s): %s." % (vm_name, opt_vm_status), ERR_CODE)
