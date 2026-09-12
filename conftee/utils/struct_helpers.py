from .constants import BLOCK_TYPE_DEVICE, BLOCK_TYPE_SECTION


def _hrch_key_format(device: str, section: str):
    """
    Description: Make formatted key name f'{device}, {section}' following conventions throughout this program.
    """
    return f"{device}, {section}"


def _build_hierarchy_from_struct(struct: list[tuple]):
    """
    Description:
        Helper function to convert file structure (list[tuple]) into two other formats.

    Args:
        struct (list[tuple]): The list of tuples representing file strucure in specialized format.

    Returns:
        dict[str, list[str]]: The file structure indict format, for easy layer relations lookup.
        list[str]: The file structure in list format, for diff compare using DifferO.
    Examples:
        Input: (1, 1, fw25-ctx, d), (2, 7, VRF, s), (8, 8, Dist switch, d), (9, 16, USER PREFIX, s)
        Output: {'fw25-ctx': ["VRF"], 'buildling dist switch': ["USER PREFIX"]}
            and {"fw25-ctx,  fw25-ctx": [1, 1], "fw25-ctx,  VRF": [2, 7], "Dist switch, Dist switch": [8, 8], "Dist switch, USER PREFIX": [9, 16]}
    """
    device_counter, section_counter = 0, 0
    current_device = ""
    hierarchy: dict[str, list[str]] = {}
    hierarchy_lines: dict[str, list[int]] = {}

    for tuple in struct:
        if tuple[3] == BLOCK_TYPE_DEVICE:
            device_counter += 1
            section_counter = 0
            current_device = tuple[2]
            hierarchy[current_device] = []
            hierarchy_lines[_hrch_key_format(current_device, current_device)] = [tuple[0], tuple[1]]

        elif tuple[3] == BLOCK_TYPE_SECTION:
            section_counter += 1
            hierarchy[current_device].append(tuple[2])
            hierarchy_lines[_hrch_key_format(current_device, tuple[2])] = [tuple[0], tuple[1]]

    return hierarchy, hierarchy_lines


def _find_device_start_end(device_name:str, struct:list[tuple],
                           hierarchy:dict[str, list[str]]) -> tuple[int, int, int]:
    """
    Description:
        Helper function to find device start line and the end of its last section.
        
    Args:
        device_name (str): Name of the device to search.
        struct (list[tuple]): The list of tuples representing file strucure in specialized format.
        hierarchy (dict[str, list[str]]): Device/section names and their line numbers, in specialized format.
    
    Returns:
        int: The start line number of the device. -1 if not found.
        int: The end line number of the device's last section. -1 if not found.
        int: The index of the device's tuple int the struct list.
    """
    start, end, idx_in_struct = -1, -1, 0
    for i in range(len(struct)):
        tuple = struct[i]
        if tuple[2] in device_name:
            start = tuple[0]
            idx_in_struct = i
            break
    
    if start >=0:
        num_of_sections = len(hierarchy[device_name])
        last_section_block = struct[idx_in_struct + num_of_sections]
        end = last_section_block[1]
    
    return start, end, idx_in_struct