import ipaddress
from enum import Enum
from typing import Union
from collections import Counter

from ..models.constants_singleton import ConstantsSingleton
from ..models.line_analyzer import LineAnalyzer
from .helpers import ipv4_in_range, calc_ipv4_range, calc_ipv4_algebra, vlan_num_in_range

from .constants import SUBNET_CLUSTERS


def _consistency_scopes(schema):
    """Variables grouped by the span over which their value must stay the same.

    Returns the `section` and `file` sets; `none` is not returned because an
    exempt variable is never looked up, it is only absent from both.

    Each variable declares its own scope, so `file` is read directly rather than
    derived by subtracting the other two from the full variable list. That
    subtraction is why adding a variable to the schema used to silently opt it
    into file-wide consistency checking.
    """
    return schema.variables_with_scope("section"), schema.variables_with_scope("file")

LNK_RELATIONS = {
  'GW-FW_outside_IP': {'USER PREFIX': "FWGLUE_Prefix_1st_IP", 'VRF': 'FWGLUE_Prefix_1st_IP',
                       'WIRELESS PREFIX': "FWGLUE_Prefix_1st_IP"}
}
ERR_TYPE_ME_DEVICE, ERR_TYPE_MISSING_DEVICE, ERR_TYPE_EXTRA_DEVICE, ERR_TYPE_MISSING_SECTION, ERR_TYPE_EXTRA_SECTION = (
    "extras-missings-in-device",
    "missing-device",
    "extra-device",
    "missing-section",
    "extra-section",
)


class METype(Enum):
    """
    Description: A custom Enum type to represent state of text units. M means missing, E means extra.
    """

    M = 1
    E = 2


def _update_m_e_device_records(
    outline_1,
    outline_2,
    diff_result,
    variables_lines,
    is_expressions_lines,
    values_lines,
    value_mismatch_lines,
    m_e_type: METype,
    device_start: int,
    device_end: int,
):
    """
    Description:
        Helper function to batch add line records within a missing/extra device.
        Update diff_result, variables_lines, is_expressions_lines, values_lines, value_mismatch_lines in-place.
    """
    if m_e_type.name == "M":
        outline = outline_1
        err_msg = ERR_TYPE_MISSING_DEVICE
    elif m_e_type.name == "E":
        outline = outline_2
        err_msg = ERR_TYPE_EXTRA_DEVICE
    else:
        raise ValueError('m_e_type must be one of "METype.M" and "METype.E"')

    # Add line for device title
    diff_result.append((err_msg, 0, 0, 0, len(outline.file_content[device_start - 1])))
    # And append annotations for all other lines in this device, but no +1 because already added that
    # for device title so -1 which becomes 0
    diff_lines = [(err_msg, 0, 0)] * (device_end - device_start)
    diff_result.extend(diff_lines)
    variables_lines.extend([[]] * (device_end - device_start + 1))
    is_expressions_lines.extend([[]] * (device_end - device_start + 1))
    values_lines.extend([[]] * (device_end - device_start + 1))
    value_mismatch_lines.extend([0] * (device_end - device_start + 1))


def _update_m_e_section_records(
    accm_line_data,
    m_e_type: METype,
    section_start: int,
    section_end: int,
):
    """
    Description:
        Helper function to batch add line records within a missing/extra section.
        Update diff_result, variables_lines, is_expressions_lines, values_lines, value_mismatch_lines in-place.
    """
    if m_e_type.name == "M":
        err_msg = ERR_TYPE_MISSING_SECTION
    elif m_e_type.name == "E":
        err_msg = ERR_TYPE_EXTRA_SECTION
    else:
        raise ValueError('m_e_type must be one of "METype.M" and "METype.E"')

    diff_lines = [(err_msg, 0, 0)] * (section_end - section_start + 1)
    accm_line_data['diff_result'].extend(diff_lines)
    accm_line_data['variables_lines'].extend([[]] * (section_end - section_start + 1))
    accm_line_data['is_expressions_lines'].extend([[]] * (section_end - section_start + 1))
    accm_line_data['values_lines'].extend([[]] * (section_end - section_start + 1))
    accm_line_data['value_mismatch_lines'].extend([0] * (section_end - section_start + 1))


def _update_device_title_record(
    accm_line_data,
    outline,
    device_start: int,
    msg: str,
):
    """
    Description:
        Helper function to add the line record for a device title line.
        Update diff_result, variables_lines, is_expressions_lines, values_lines, value_mismatch_lines in-place.
    """
    accm_line_data['diff_result'].append((msg, 0, 0, 0, len(outline.file_content[device_start - 1])))
    accm_line_data['variables_lines'].append([])
    accm_line_data['is_expressions_lines'].append([])
    accm_line_data['values_lines'].append([])
    accm_line_data['value_mismatch_lines'].append(0)


def _collect_var_val_dicts(
    var_val_dict_full: dict[str, list], var_val_dict: dict[str, list], device_name: str, section_name: str
):
    """
    Description:
        Merge section var_val_dict into var_val_dict_full for the whole config.
        Update var_val_dict_full in-place.
    """
    for var in var_val_dict:
        new_vals_info = []
        for val_info in var_val_dict[var]:
            # Because input var_val_dict has no record of device and section names, append those
            new_val_info = [val_info[0], val_info[1], device_name, section_name]
            new_vals_info.append(new_val_info)

        if var in var_val_dict_full:
            var_val_dict_full[var].extend(new_vals_info)
        else:
            var_val_dict_full[var] = new_vals_info


def _collect_var_incons(variable_incons: dict[str, list], var_val_dict: dict[str, list], schema, **kwargs):
    """
    Description:
        Check and collect inconsistent values in a section or whole file.

    Args:
        variable_incons (dict[str, list]): The dict storing inconsistent variables and their line numbers collected so far.
        var_val_dict (dict[str, list]): The dict storing variables and their values already collected from a section or whole config.
        schema (Schema): The vocabulary that declares each variable's consistency scope.
        **kwargs: Either a dict with keys 'device_name' and  'section_name' for a sections, or none for a whole config.

    Returns:
        None. This function only reads var_val_dict and modifies variable_incons in-place.

    Examples:
        Input: var_val_dict is {'Vlan_ID_user': [['645', 9], ['789', 12]]},
                variable_incons is [],
                kwargs is {device_name="fw25-ctx", section_name="VRF"};
        Output: variable_incons becomes ['fw25-ctx, VRF', 'Vlan_ID_user', [9, 12]],
                because this is section level detection and {Vlan_ID_user} has 2 values 645, 789.

        Input: var_val_dict is {'RD_ID': [['34435', 5], ['3435', 6]], 'Vlan_ID_user': [['645', 9], ['789', 12]], 'FW_context_name': [['ABCD12', 10]], 'VRF_name': [['abcd-xy12', 10]]},
                variable_incons is [['fw25-ctx, VRF', 'Vlan_ID_user', [9, 12]]],
                kwargs is none;
        Output: variable_incons becomes [['fw25-ctx, VRF', 'Vlan_ID_user', [9, 12]], ['File', 'RD_ID', [5, 6]]],
                because this is whole file level detection and {RD_ID} has 2 values 34435, 3435.
    """

    var_cons_section, var_cons_file = _consistency_scopes(schema)

    if len(kwargs) == 2 and "device_name" in kwargs and "section_name" in kwargs:
        constant_dict = var_cons_section
        device_name = kwargs["device_name"]
        section_name = kwargs["section_name"]
        extra_val_info = [device_name, section_name]
    elif len(kwargs) == 0:
        constant_dict = var_cons_file
        extra_val_info = []
    else:
        print("Incorrect **kwargs input for _collect_var_incons(.).")
        return
    for var in var_val_dict:
        # Collect values under this variable and see if they equal one another
        vals = [val_on_line[0] for val_on_line in var_val_dict[var]]
        has_different_vals = not (len(set(vals)) == 1)
        # If values under a variable is >1, and it should be consistent within a section or whole config,
        # and the values are different, then this is an inconsisitency
        if (len(var_val_dict[var]) > 1) and (var in constant_dict) and has_different_vals:
            new_vals_info = []
            for val_info in var_val_dict[var]:
                new_val_info = val_info + extra_val_info
                new_vals_info.append(new_val_info)

            if var in variable_incons:
                variable_incons[var].extend(new_vals_info)
            else:
                variable_incons[var] = new_vals_info


def _find_first_most_common(val_list: Union[list[str], list[int]], fallback: Union[str, int]):
    """
    Description:
        Inner helper to find the first most common element in a list.
    """
    if not val_list:
        return fallback
    counter = Counter(val_list)
    most_common_vals = [val for val, count in counter.items() if count == counter.most_common(1)[0][1]]
    result = val_list[val_list.index(next(iter(most_common_vals)))]
    return result

def _variable_is_demarcation_ip(var:str):
    """
    Description:
        Helper to determine if a variable should be 1st or last ip variable.

    Returns:
        int|None: 1 means 1st, 2 means last, None means not a demarcation ip variable.
    """
    var_lower = var.lower()
    dm_type = None
    if "first_ip" in var_lower or "1st_ip" in var_lower:
        dm_type = 1
    elif "last_ip" in var_lower:
        dm_type = 2
    
    return dm_type

def _determine_correct_values(var_val_dict_full: dict[str, list[list]], infra_prefixes: dict, schema) -> dict[str, str]:
    """
    Description:
        Determine the correct values for variables. Currently just pick the most frequent ones. Might change later.
    """
    var_cons_section, _ = _consistency_scopes(schema)
    # One analyzer for the whole pass; it was previously rebuilt per value.
    la = LineAnalyzer(schema)

    result = {}
    for var in var_val_dict_full:
        if var in var_cons_section:
            curr_device, curr_section = var_val_dict_full[var][0][2], var_val_dict_full[var][0][3]
            vals_in_sections = {}
            vals_in_sections[curr_device] = {}
            vals_in_sections[curr_device][curr_section] = []
            for val_in_section in var_val_dict_full[var]:
                device, section = val_in_section[2], val_in_section[3]

                # Handle cases where device or section changes
                if (device == curr_device) and (section != curr_section):
                    # Section change. Find the most common value in last section
                    first_most_common_val = _find_first_most_common(
                        vals_in_sections[curr_device][curr_section], fallback="{" + var + "}"
                    )
                    vals_in_sections[curr_device][curr_section] = first_most_common_val
                    # Then update pointer and create entries
                    curr_section = section
                    vals_in_sections[curr_device][curr_section] = []
                elif device != curr_device:
                    # Device change. Find the most common value in last section
                    first_most_common_val = _find_first_most_common(
                        vals_in_sections[curr_device][curr_section], fallback="{" + var + "}"
                    )
                    vals_in_sections[curr_device][curr_section] = first_most_common_val
                    # Then update pointer and create entries
                    curr_device, curr_section = device, section
                    vals_in_sections[curr_device] = {}
                    vals_in_sections[curr_device][curr_section] = []

                # Only append value if it is valid
                if la.variable_is_value_match(var, val_in_section[0]):
                    vals_in_sections[curr_device][curr_section].append(val_in_section[0])

            # Finally do the same for the overall last section
            first_most_common_val = _find_first_most_common(
                vals_in_sections[curr_device][curr_section], fallback="{" + var + "}"
            )
            vals_in_sections[curr_device][curr_section] = first_most_common_val
            result[var] = vals_in_sections
        else:
            # Currently if a variable is not a section cons variable, it is a file cons one
            vals = [val_on_line[0] for val_on_line in var_val_dict_full[var]]
            # Eliminate all values that does not match the regex
            vals_valid = []
            for i in range(len(vals)):
                if la.variable_is_value_match(var, vals[i]):
                    vals_valid.append(vals[i])

            first_most_common_val = _find_first_most_common(vals_valid, fallback="{" + var + "}")
            result[var] = first_most_common_val

    # Finally overwrite/append infrastructure IP ranges with those supplied by the caller.
    # These come from the deployment's own source of truth (an API response, or the
    # fixture dict the sample corpus ships with), so there is no built-in fallback:
    # passing none simply means no infrastructure prefixes are known.
    for k, v in (infra_prefixes or {}).items():
        # Loop and add infra IPs into this dictionary. Important: Keep the key names exactly the same as in constants.py.
        if v['prefix_type'] == "fwglue":
            fwglue_range_start, fwglue_range_end = calc_ipv4_range(ip=v['prefix'][:-3], cidr_mask=v['prefix'][-3:])
            result["FWGLUE_Prefix"] = fwglue_range_start
            result["FWGLUE_Prefix_1st_IP"] = calc_ipv4_algebra(ip=fwglue_range_start, operator="+", operand=1)
            result["FWGLUE_Prefix_last_IP"] = calc_ipv4_algebra(ip=fwglue_range_end, operator="-", operand=1)
            
        elif v['prefix_type'] == "vrfglue":
            vrfglue_range_start, vrfglue_range_end = calc_ipv4_range(ip=v['prefix'][:-3], cidr_mask=v['prefix'][-3:])
            result["Vrfglue_prefix"] = vrfglue_range_start
            result["Vrfglue_prefix_1st_IP"] = calc_ipv4_algebra(ip=vrfglue_range_start, operator="+", operand=1)
            result["Vrfglue_prefix_last_IP"] = calc_ipv4_algebra(ip=vrfglue_range_end, operator="-", operand=1)

    return result


def _lookup_correct_values(var: str, correct_values: dict[str, str], schema, device_name: str = "", section_name: str = ""):
    """
    Description:
        Lookup the correct values for variables. This function is tightly coupled with _determine_correct_values(.)'s
        output. So if that changes, this has to be changed.
    """
    var_cons_section, _ = _consistency_scopes(schema)

    correct_val: str = ""
    consistency_type: int = -1
    try:
        if var in var_cons_section:
            correct_val = correct_values[var][device_name][section_name]
            consistency_type = 1
        else:
            correct_val = correct_values[var]
            consistency_type = 0
    except ValueError:
        print(f"_lookup_correct_values(.) did not find any correct value for {var}")

    return correct_val, consistency_type


# What a pool violation is called in a report, keyed by the pool's name. The
# engine's finding types are part of its output contract, so they stay fixed
# here rather than being derived from whatever a schema happens to name a pool.
POOL_FINDING_TYPES = {
    "user_ipv4": "user-ipv4-pool",
    "infra_ipv4": "infra-ipv4-pool",
    "user_vlan": "user-vlan-pool",
    "infra_vlan": "infra-vlan-pool",
}


def _value_is_in_pool(var: str, val: str, section_name: str, schema):
    """
    Description:
        Determine if a value for a variable is in a schema-defined pool range or not.

    A variable with no pool is not checked. That is the point of moving pools into
    the schema: the ranges were an organization's own, and a deployment that does
    not declare them gets no pool findings rather than findings against ranges
    inherited from the network this tool was written for.

    The section-conditional VLAN check the hardcoded version did is gone. It picked
    the infrastructure pool outside USER PREFIX and the user pool inside it, but
    both pools held the identical range, so the branch could not change a verdict.
    Expressing it in the schema would have meant a per-section pool construct built
    for a distinction nothing currently makes; a schema that needs one can declare
    a separate variable. See tests/test_schema_equivalence.py, which pins the two
    ranges as equal and fails if they ever diverge.
    """
    wrong_pool_type = None
    correct_pool = []

    pool = schema.pool_for(var)
    if pool is None:
        return wrong_pool_type, correct_pool

    if pool.kind == "ipv4":
        low, high = calc_ipv4_range(ip=pool.ip, cidr_mask=pool.mask)
        if not ipv4_in_range(val, low, high):
            wrong_pool_type = POOL_FINDING_TYPES[pool.name]
            correct_pool = [low, high]
    else:
        if not vlan_num_in_range(int(val), pool.start, pool.end):
            wrong_pool_type = POOL_FINDING_TYPES[pool.name]
            correct_pool = [str(pool.start), str(pool.end)]

    return wrong_pool_type, correct_pool

def _value_is_demarcation_ip(val:str, dm_type:int, subnet_range:list[str]):
    """
    Description:
        Helper to determine if a value should be 1st or last ip value.
        This function is tightly coupled with _variable_is_demarcation_ip(.).

    Returns:
        int|None: 1 means 1st, 2 means last, None means not a demarcation ip variable.
    """
    wrong_dm_ip_type = None
    correct_dm_ip = []

    if subnet_range[0] == subnet_range[1]:
        first_ip, last_ip = subnet_range[0], subnet_range[0]
    else:
        first_ip = calc_ipv4_algebra(subnet_range[0], "+", 1)
        last_ip = calc_ipv4_algebra(subnet_range[1], "-", 1)

    if dm_type == 1:
        # This means it should be the value for a first ip variable
        if val != first_ip:
            wrong_dm_ip_type = "subnet-first-ip"
            correct_dm_ip = [first_ip, first_ip]
    elif dm_type == 2:
        # This means it should be the value for a first ip variable
        if val != last_ip:
            wrong_dm_ip_type = "subnet-last-ip"
            correct_dm_ip = [last_ip, last_ip]
    
    return wrong_dm_ip_type, correct_dm_ip

def _value_is_wrong_sourced(var: str, val: str, correct_values: dict, section_name: str, schema):
    """
    Description:
        Determine if a value for a variable is in correct ranges or not. Correct ranges currently include
        globally defined pools and subnet ranges locally calculated from info in a config.
    """
    # A correctly sourced value should be:  1. From correct pool, if applicable
    #                                       2. Be in the correct subnet, if applicable

    # Here is to verify restriction 1.
    wrong_source_type, correct_source = _value_is_in_pool(var, val, section_name, schema)

    # Here is to verify restriction 2; restriction 2 takes precedence over restriction 1
    cs = ConstantsSingleton.get_instance()
    cs_dict = ConstantsSingleton.get_clusters_dict()
    cluster = cs.find(var)
    is_var_a_netmask = "netmask" in var
    if cluster in SUBNET_CLUSTERS and not is_var_a_netmask:
        # If variable is in a subnet cluster, and it is not a netmask, the value should be in this subnet's range
        tmp_val = ""
        for cluster_var in cs_dict[cluster]:
            if "netmask" not in cluster_var:
                try:
                    tmp_val = str(ipaddress.IPv4Address(correct_values[cluster_var]))
                    tmp_wrong_pool_type, tmp_correct_source = _value_is_in_pool(cluster_var, tmp_val, section_name, schema)
                    if not tmp_wrong_pool_type:
                        # If found a value in the cluster that is from the correct pool, break
                        # and tmp_val should be storing a valid IP address
                        break
                    else:
                        # If not in the correct pool, reset tmp_val to empty to store the next candidate
                        tmp_val = ""
                except Exception as e:
                    # This means the global correct value for this variable does not exist, e.g. recorded as {var}
                    tmp_val = ""

        if tmp_val == "":
            # This means either none of the subnet variable members has value from correct pool, or none of them is in IPv4 format
            # So don't do anything to previous wrong_source_type, falling back on the result of restriction 1 check.
            pass

        else:
            # This means there is a valid subnet Ipv4 address and we can check the subnet range
            try:
                # Search for the variable name for mask in this clusters
                mask_var = ""
                for cluster_var in cs_dict[cluster]:
                    if "netmask" in cluster_var:
                        mask_var = cluster_var
                        break
                
                mask_val = correct_values[mask_var]
            except KeyError:
                mask_val = ""

            if mask_val and "{" not in mask_val:
                # If a netmask value is in the correct value dict, and it is not the variable name like {var},
                # we can calculate the subnet range and check the passed-in val
                tmp_subnet_range = calc_ipv4_range(ip=tmp_val, sub_mask=mask_val)
                dm_type = _variable_is_demarcation_ip(var)

                # Then determine the error type based on the subnet range
                if not ipv4_in_range(ip=val, start_ip=tmp_subnet_range[0], end_ip=tmp_subnet_range[1]):
                    # If the value is not in the range at all, then simply report out of range error
                    wrong_source_type = cluster + "-subnet"
                    correct_source = tmp_subnet_range
                elif dm_type:
                    # If the value is in the range, then further check if it is the 1st or last IP, if applicable
                    tmp_wrong_ip_type, tmp_correct_ip = _value_is_demarcation_ip(val=val, dm_type=dm_type, subnet_range=tmp_subnet_range)
                    if tmp_wrong_ip_type:
                        wrong_source_type = tmp_wrong_ip_type
                        correct_source = tmp_correct_ip

    return bool(wrong_source_type), str(wrong_source_type), correct_source


def _value_is_wrong_link(
    var: str, val: str, correct_values: dict, var_val_dict_full: dict[str, list[list[Union[str, int]]]], section_name: str
) -> tuple[bool, str, str]:
    link_var_dict = LNK_RELATIONS.get(var, {})
    link_var = link_var_dict.get(section_name, "")
    
    if not link_var_dict or not link_var:
        raise ValueError(f"Variable {var}'s linked variable is not found in relationship table.")

    # Look up the correct up stream value
    wrong_link_type = ""
    correct_link_val = correct_values.get(link_var, "")

    if not correct_link_val:
        return False, "up-link-not-found", ""
    elif correct_link_val and correct_link_val != val:
        wrong_link_type = "wrong-gateway"

    return bool(wrong_link_type), wrong_link_type, correct_link_val
