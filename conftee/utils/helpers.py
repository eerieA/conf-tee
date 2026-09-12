import re, ipaddress
from mako.template import Template

from .constants import GENERAL_IPV4_REGEX, GENERAL_CIDR_MASK_REGEX

def string_to_int_safe(string:str):
    """
    Description:
        Helper function to supress ValueError when converting string to int.
    """
    try:
        result = int(string)
    except Exception as e:
        return None
    
    return result

def reverse_operator(operator:str):
    """
    Description:
        Helper function to "reverse" some algebraic operators as strings.
    """
    if operator != "+" and operator != "-":
        return None
     
    if operator == "+":
        return "-"
    else:
        return "+"

def calc_ints_string_op(operand1:int, operator:str, operand2:int):
    """
    Description:
        Helper function to calculate results of an algebra expression where operator is a string.
        Currently only supports "+" and "-".
    """
    if operator != "+" and operator != "-":
        return None
    
    if operator == "+":
        return operand1 + operand2
    else:
        return operand1 - operand2

def cidr_mask_to_list(cidr_digit:int):
    """
    Description:
        Helper function to convert cidr mask into list of octets.
    
    Examples:
        Input: cidr_digit is 21
        Output: [0b11111111, 0b11111111, 0b11111000, 0b00000000]
    """
    result = [0b00000000, 0b00000000, 0b00000000, 0b00000000]

    if cidr_digit < 0 or cidr_digit > 32:
        return result
    
    index1, index2 = divmod(cidr_digit, 8)    
    i = index1
    while i > 0:
        result[i-1] = 0b11111111
        i -= 1
    
    bitmask = (1 << (8 - index2)) - 1
    result[index1] = 0b11111111 ^ bitmask

    return result

def calc_ipv4_range(ip:str, sub_mask:str="", cidr_mask:str=""):
    """
    Description:
        Helper function to calculate ipv4 range using given ipv4 address and masks.
    
    Examples:
        Input: ip is "137.14.33.45", sub_mask is "255.255.248.0"
        Output: "137.14.32.0" and "137.14.39.255"
        Input: ip is "137.14.33.45", cidr_mask is "/15"
        Output: "137.14.0.0" and "137.15.255.255"
    """
    if not ip or (not sub_mask and not cidr_mask):
        raise ValueError("Empty ip, or no subnet mask and no cidr mask.")
    
    # At this point it is certain at least one of sub_mask and cidr_mask is not empty    
    ip_match = re.fullmatch(GENERAL_IPV4_REGEX, ip)
    sub_mask_match = re.fullmatch(GENERAL_IPV4_REGEX, sub_mask)
    cidr_mask_match = re.fullmatch(GENERAL_CIDR_MASK_REGEX, cidr_mask)
    if not ip_match:
        raise ValueError("Ip format incorrect.")
    
    # Prioritize subnet mask over cidr mask by setting type as subnet mask as long as it is
    # not empty and has correct format
    mask_octets, mask_digit = [], -1
    if bool(sub_mask_match):
        mask_type = 0
        mask_octets = [int(seg) for seg in sub_mask.split('.')]
    elif bool(cidr_mask_match):
        mask_type = 1
        mask_digit = int(cidr_mask[1:])
    else:
        raise ValueError("No valid ipv4 range mask was provided.")
    
    ip_octets = [int(seg) for seg in ip.split('.')]

    # Translate segment form to/from cidr digits depending on type of mask notation
    if mask_type == 0:
        binary_mask_str = ''.join(format(seg, '08b') for seg in mask_octets)
        mask_digit = sum(1 for bit in binary_mask_str if bit == '1')
    elif mask_type == 1:
        mask_octets = cidr_mask_to_list(mask_digit)

    start_address_octets = []
    for i in range(0, 4):
        start_address_octets.append(ip_octets[i] & mask_octets[i])
    
    num_addresses = 2**(32 - mask_digit)
    start_address = '.'.join(map(str, start_address_octets))
    subnet = ipaddress.ip_network(start_address + '/' + str(mask_digit), strict=False)
    if num_addresses >= 2**32:
        # 4294967296 (>= 2**32) is not permitted as an IPv4 address
        end_address = "255.255.255.255"
    else:
        end_address = subnet.network_address + (num_addresses - 1)
    #end_address_octets = list(map(int, str(end_address).split('.')))

    return start_address, str(end_address)

def calc_ipv4_algebra(ip:str, operator:str, operand: int):
    """
    Description:
        Do simple algebra in an expresssion with an IPv4 address.
    """
    ip_int = int(ipaddress.IPv4Address(ip))
    result = ""
    if operator == "+":
        result = ipaddress.ip_address(min(4294967294, ip_int) + operand)
    elif operator == "-":
        result = ipaddress.ip_address(max(1, ip_int) - operand)
    
    return str(result)

def ipv4_in_range(ip:str, start_ip:str, end_ip:str):
    """
    Description:
        Determine if an ipv4 address is within range of given start and end ips.
    """
    ip_int = int(ipaddress.IPv4Address(ip))
    start_ip_int = int(ipaddress.IPv4Address(start_ip))
    end_ip_int = int(ipaddress.IPv4Address(end_ip))

    return start_ip_int <= ip_int <= end_ip_int

def vlan_num_in_range(vlan_num:int, start:int, end:int):
    """
    Description:
        Determine if a Vlan number/ID is within range of given start and end numbers.
    """
    return start <= vlan_num <= end


def get_legit_ip_pools():
    """
    Description:
        Determine ip pool ranges.
    Args:
        None.
    """
    # Current values are specifically for integration tests. Live network env have various
    # smaller ranges, and the infrastructural an user pools will be different ranges.
    tmp_ip_pool_infra = {"ip": "10.45.0.0", "mask": "/16"}
    tmp_ip_pool_user = {"ip": "10.45.0.0", "mask": "/16"}

    return tmp_ip_pool_infra, tmp_ip_pool_user


def get_legit_vlan_pools():
    # Current values are specifically for integration tests. Real network env don't have
    # such large ranges, and the infrastructural an user pools will be different ranges.
    tmp_vlan_pool_infra = {'start': 1, 'end': 4096}
    tmp_vlan_pool_user = {'start': 1, 'end': 4096}

    return tmp_vlan_pool_infra, tmp_vlan_pool_user


def quick_is_device_title(line: str):
    """
    Determine if a line is likely a device title, in a quick and less reliable way.
    """
    return line[0:3] == "~~~"


def quick_is_section_title(line: str):
    """
    Determine if a line is likely a section title, in a quick and less reliable way.
    """
    return line[0:3] == "! #"

def replace_device_titles_in_response(resp_dict:dict[str, list[str]], devices_g:list[str]):
    """
    Description:
        Replace device names in the response from endpoint with device names in corresponding golden config.
        Because test fixture names change per run. So this is a semi-temporary approach. May become obsolete later.
    """
    result = {}
    for i, (key, value) in enumerate(resp_dict.items()):
        new_key = devices_g[i]
        result[new_key] = value
    return result

def replace_device_titles_in_golden(golden_file_path:str, device_names:list[str]):
    with open(golden_file_path, 'r') as f:
        template_string = f.read()

    template = Template(template_string)

    render_args = {}
    for i in range(len(device_names)):
        key = "device_" + "{:03d}".format(i+1)
        render_args[key] = device_names[i]

    output_text = template.render(**render_args)
    output_lines = output_text.split('\n')
    
    return output_lines

def search_key_in_dict(dictionary: dict, key: str):
    """
    Description:
        Recursively find all keys in a dict with a given name and collect their values.
    """
    results = []

    if isinstance(dictionary, dict):
        for k, v in dictionary.items():
            if k == key:
                results.append(v)
            elif isinstance(v, (dict, list)):
                results.extend(search_key_in_dict(v, key))
    elif isinstance(dictionary, list):
        for item in dictionary:
            results.extend(search_key_in_dict(item, key))

    return results


def get_prefixes_from_response(data: dict):
    """
    Description:
        Collect important IP prefixes from API responses.
    Args:
        data (dict): The data part of a relevant API response, such as: job_send_response['results'][0].
                    The data should be with a certain structure. If the structure from API changes,
                    this function should change.
    """
    search_result = search_key_in_dict(data, "prefix")

    # Current response structures may have "prefix" keys with either dict or str values, we want the dicts
    prefix_dicts: list[dict] = []
    for item in search_result:
        if isinstance(item, dict):
            prefix_dicts.append(item)

    # Build name and info correspondence dict
    prefix_name_dict = {}
    for pref_dict in prefix_dicts:
        prefix_name_dict[pref_dict['name']] = {'prefix': pref_dict['prefix'], 'prefix_type': pref_dict['prefix_type']}

    return prefix_name_dict
