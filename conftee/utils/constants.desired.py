# Constants for desired production purposes, some values are different than in constants.tests.py

# The dictionary that maps word types to regular expressions
# Directly copied from version 1 of this program (now stowed under ./v1)
# A bit clunky but decided to keep them as they are since this works fine
WORD_TYPE_REGEXES = {
    "Vlan_ID_fwglue": r"[1-9]\d{0,3}",
    "Vlan_ID_vrfglue": r"[1-9]\d{0,3}",
    "Vlan_ID_vpnglue": r"[1-9]\d{0,3}",
    "Vlan_ID_user": r"[1-9]\d{0,3}",
    "Vlan_name": r"[A-Z]{4}\d{2}-[\w-]+=[A-Z]{4}-[^_\s]+$",
    "net_type_5_Vlan_name": r"[A-Z]{4}\d{2}-[\w-]+",
    "net_type_4_Vlan_name": r"[A-Z]{4}\d{2}-[\w-]+=(DNET-USER|RESN-USER)",
    "net_type_6_Vlan_name": r"[^\d-=._][\w-=._]*",
    "RD_ID": r"[1-9]\d{0,3}$",
    "RD_#": r"[1-9]\d{0,3}$",
    "VRF_name": r"[A-Z]{4}-[^_\s]+",
    "net_type_4_VRF_name": r"(DNET-USER|RESN-USER)",
    "FW_context_name": r"[A-Z]{4}\d{2}",
    "IP_local_pool_name": r"[a-z0-9]+(?:\.[a-z0-9]+)*",
    "IBVPN_metric": r"(2[0-4][0-9]|25[0-4]|[2-9]|[1-9][0-9])",
    "OSPF_area_#": r"(?:\d|[1-9]\d{1,2})",
    "int_#": r"[1-9](\/[1-9](\/[1-9][0-9]?)?)?",
    "password": r"[^\s]+",
    "key_word": r"[^\s]+",
    "int_name_A": r"(GigabitEthernet|TenGigabitEthernet|FortyGigabitEthernet)",
    "int_name_L": r"(GigabitEthernet|TenGigabitEthernet|FortyGigabitEthernet)",
    "Vrfglue_prefix_netmask": r"255.255.255.248",
    "Inv_Vrfglue_prefix_netmask": r"0.0.0.7",
    "FWGLUE_Prefix_netmask": r"255.255.255.248",
    "Inv_FWGLUE_Prefix_netmask": r"0.0.0.7",
    "Vpnglue_prefix_netmask": r"255.255.255.248",
    "Inv_Vpnglue_prefix_netmask": r"0.0.0.7",
    "User_prefix": r"([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
    "User_prefix_netmask": r"([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
    "User_Prefix_last_IP": r"([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
    "IP_local_pool_first_IP": r"([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
    "IP_local_pool_last_IP": r"([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
    "IP_local_pool_prefix": r"([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
    "IP_local_pool_netmask": r"([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
    "Vrfglue_prefix": r"([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
    "Vrfglue_prefix_1st_IP": r"([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
    "Vrfglue_prefix_last_IP": r"([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
    "FWGLUE_Prefix": r"([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
    "FWGLUE_Prefix_last_IP": r"([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
    "FWGLUE_Prefix_1st_IP": r"([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
    "Vpnglue_prefix": r"([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([1-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
    "Vpnglue_prefix_1st_IP": r"([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([1-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
    "Vpnglue_prefix_last_IP": r"([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([1-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
    "GW-FW_outside_IP": r"([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
    "GW-FW_inside_IP": r"([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
    "GW-VRFGLUE_IP": r"([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
    "IP_helper_address": r"([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([1-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
    "mdt_default_address": r"239\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([1-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
    "mdt_data_address": r"239\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.([1-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])"
}

# These are variable names that should have values that are a subset of IPv4 addresses
IPV4_VARIABLES = [
    "Vrfglue_prefix_netmask",
    "Inv_Vrfglue_prefix_netmask",
    "FWGLUE_Prefix_netmask",
    "Inv_FWGLUE_Prefix_netmask",
    "Vpnglue_prefix_netmask",
    "Inv_Vpnglue_prefix_netmask",
    "User_prefix",
    "User_prefix_netmask",
    "User_Prefix_last_IP",
    "IP_local_pool_first_IP",
    "IP_local_pool_last_IP",
    "IP_local_pool_prefix",
    "IP_local_pool_netmask",
    "Vrfglue_prefix",
    "Vrfglue_prefix_1st_IP",
    "Vrfglue_prefix_last_IP",
    "FWGLUE_Prefix",
    "FWGLUE_Prefix_1st_IP",
    "FWGLUE_Prefix_last_IP",
    "Vpnglue_prefix",
    "Vpnglue_prefix_1st_IP",
    "Vpnglue_prefix_last_IP",
    "GW-FW_outside_IP",
    "GW-FW_inside_IP",
    "GW-VRFGLUE_IP",
    "IP_helper_address",
    "mdt_default_address",
    "mdt_data_address"
]

IPV4_VARIABLES_USER = ["User_prefix", "User_Prefix_last_IP"]

IPV4_VARIABLES_INFRA = [
    "Vrfglue_prefix",
    "Vrfglue_prefix_1st_IP",
    "Vrfglue_prefix_last_IP",
    "FWGLUE_Prefix",
    "FWGLUE_Prefix_1st_IP",
    "FWGLUE_Prefix_last_IP",
    "Vpnglue_prefix",
    "Vpnglue_prefix_1st_IP",
    "Vpnglue_prefix_last_IP",
    "GW-FW_outside_IP",
    "GW-FW_inside_IP",
    "GW-VRFGLUE_IP",
]

INT_VARIABLES = ["Vlan_ID_fwglue", "Vlan_ID_vrfglue", "Vlan_ID_user", "RD_ID", "RD_#", "OSPF_area_#"]

# GENERAL_IPV4_REGEX is for detecting general IPv4 addresses as a whole, without restricting 0-255 for octets
GENERAL_IPV4_REGEX = r"(?:[0-9]{1,3}\.){3}[0-9]{1,3}"
GENERAL_CIDR_MASK_REGEX = r"\/(3[0-2]|[1-2]{0,1}[0-9])"

# For determining which variables should be in a same subnet (by ConstantsSingleton); using all lower case for safty
# Reminder: exclude clusters that should not be checked for higher level consistency, such as ip_local_pool cluster
SUBNET_CLUSTERS = ["user_prefix", "vrfglue_prefix", "fwglue_prefix", "vpnglue_prefix"]

BLOCK_TYPE_DEVICE, BLOCK_TYPE_SECTION = "d", "s"
