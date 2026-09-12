from collections import Counter

from .differ_o import DifferO
from .outline import Outline
from .section_comparer import SectionComparer
from ..utils import struct_helpers, diff_helpers

from ..utils.diff_helpers import (
    METype,
    ERR_TYPE_ME_DEVICE,
    ERR_TYPE_MISSING_DEVICE,
    ERR_TYPE_EXTRA_DEVICE,
    ERR_TYPE_MISSING_SECTION,
    ERR_TYPE_EXTRA_SECTION,
)
from .section_comparer import COL_LABEL_LINE_CONTENT, COL_LABEL_LINE_NUM_1, COL_LABEL_LINE_NUM_2
from ..utils.constants import BLOCK_TYPE_DEVICE, BLOCK_TYPE_SECTION


class ConfigCompare:

    def __init__(self, file_data, outline_data: list[Outline]):
        """
        Description:
            Instantiate. This class handles pre and post processing of diff checking. It is designed as the "main" class for outside modules and programs.
            Currently it only works for texts that has at least 1 device and 1 section. Does not deal with others such as only 1 section.

        Args:
            content_1 (list[str]): Input data 1. Ideally collected from the golden config file.
            content_2 (list[str]): Input data 2. Ideally collected from the user config JSON object.
        """
        self.file_struct_1 = file_data[0]
        self.file_struct_2 = file_data[1]
        self.outline_1 = outline_data[0]
        self.outline_2 = outline_data[1]

    def compare_structs(self):
        """
        Description:
            Compare file structures in hierarchically, and collect missing/extra devices and sections.

        Returns:
            dict[str, list[str]], dict[str, list[str]]: File structure 1 and 2 in specialized dict format.
            dict[str, list[int]], dict[str, list[int]]: File structure 1 and 2 flattend but with line number ranges.
            dict[str, list[str]]: Missing devices/sections in specialized dict format.
            dict[str, list[str]]: Extra devices/sections in specialized dict format.
            list[str]: Names of devices merged from those in outlines 1 and 2.
            list[str]: Names of entirly missing device blocks.
            list[str]: Names of entirly extra device blocks.

        Examples:
            Input: outline_1 has (1, 1, fw25-ctx, d), (2, 7, VRF, s), (8, 8, vss-a25-l25, d), (9, 14, VRF, s), (15, 15, vss-a26-l26, d), (16, 20, VRF, s),
                outline_2 has (1, 1, fw25-ctx, d), (2, 6, CONTEXT, s), (7, 12, VRF, s), (13, 13, bl31asa, d), (14, 19, VRF, s), (20, 20, vss-a25-l25, d), (21, 26, VRF, s).
            Output: hierarchy_1: {'fw25-ctx': ['VRF'], 'vss-a25-l25': ['VRF'], 'vss-a26-l26': ['VRF']}
                    hierarchy_2: {'fw25-ctx': ['CONTEXT', 'VRF'], 'bl31asa': ['VRF'], 'vss-a25-l25': ['VRF']}
                    hierarchy_lines_1: {"fw25-ctx,  fw25-ctx": [1, 1], "fw25-ctx,  VRF": [2, 7], ...}
                    hierarchy_lines_2: {"fw25-ctx,  fw25-ctx": [1, 1], "fw25-ctx,  CONTEXT": [2, 6], ...}
                    missings: {'vss-a26-l26': ['VRF']}
                    extras: {'bl31asa': ['VRF'], 'fw25-ctx': ['CONTEXT']}
                    devices_2_adj: ['fw25-ctx', 'bl31asa', 'vss-a25-l25', 'vss-a26-l26']
                    missing_device_names: ['vss-a26-l26']
                    extra_device_names: ['bl31asa']
        """

        hierarchy_1, hierarchy_lines_1 = struct_helpers._build_hierarchy_from_struct(self.file_struct_1)
        hierarchy_2, hierarchy_lines_2 = struct_helpers._build_hierarchy_from_struct(self.file_struct_2)

        # Firstly compare device differences. Initialize 2 dicts and 2 lists to store them.
        missings, extras = {}, {}
        missing_device_names, extra_device_names = [], []
        missing_section_names, extra_section_names = [], []

        # Warning: Adjust DifferO's cutoff according to latest situation, so that the program can correctly compare device blocks.
        #       For example if golden has "~~ fw25-ctx FW context ~~" and user has "~~ fw25-ctxm FW context ~~"
        #       and cutoff=0.9, then Differ determines fw25-ctx is the same as fw25-ctxm, but hierarchy_1 will
        #       not have a key called 'fw25-ctxm' and will throw a KeyError. So current cutoff is set to 0.98.
        differ_o = DifferO(cutoff=0.98)
        comp_res = differ_o.compare(list(hierarchy_1.keys()), list(hierarchy_2.keys()))
        df, _, missing_devices, extra_devices = differ_o.seperate_line_ops(comp_res)

        devices_2_adj = df[COL_LABEL_LINE_CONTENT].values.tolist()

        for missing_device in missing_devices:
            # Lookup the missing device's name in the dataframe
            # Because it is certain that line numbers are unique, only have to get values[0]
            missing_device_name = str(
                df.loc[df[COL_LABEL_LINE_NUM_1] == missing_device, COL_LABEL_LINE_CONTENT].values[0]
            )
            missings[missing_device_name] = hierarchy_1[missing_device_name]
            missing_device_names.append(missing_device_name)

        for extra_device in extra_devices:
            # Similar processing as missing devices
            extra_device_name = str(df.loc[df[COL_LABEL_LINE_NUM_2] == extra_device, COL_LABEL_LINE_CONTENT].values[0])
            extras[extra_device_name] = hierarchy_2[extra_device_name]
            extra_device_names.append(extra_device_name)

        # Secondly, compare section block missings/extras
        device_ordered = list(hierarchy_2.keys())
        for device in device_ordered:
            if device not in missings.keys() and device not in extras.keys():
                # If a device is not completly missing/extra, compare its sections with its couterpart's in outline 1; need a high cutoff for low tolerence of in-line differences
                differ_o = DifferO(cutoff=0.9)
                comp_res = differ_o.compare(hierarchy_1[device], hierarchy_2[device])
                df, _, missing_sections, extra_sections = differ_o.seperate_line_ops(comp_res)

                # If it has missing/extra sections, add dict key to store them.
                if missing_sections:
                    missings[device] = []
                if extra_sections:
                    extras[device] = []

                # And add missing/extra sections into those lists
                for missing_section in missing_sections:
                    missing_section_name = str(
                        df.loc[df[COL_LABEL_LINE_NUM_1] == missing_section, COL_LABEL_LINE_CONTENT].values[0]
                    )
                    missings[device].append(missing_section_name)
                    missing_section_names.append(missing_section_name)

                for extra_section in extra_sections:
                    extra_section_name = str(
                        df.loc[df[COL_LABEL_LINE_NUM_2] == extra_section, COL_LABEL_LINE_CONTENT].values[0]
                    )
                    extras[device].append(extra_section_name)
                    extra_section_names.append(extra_section_name)

        return {
            "hierarchy_1": hierarchy_1,
            "hierarchy_lines_1": hierarchy_lines_1,
            "hierarchy_2": hierarchy_2,
            "hierarchy_lines_2": hierarchy_lines_2,
            "struct_missings": missings,
            "struct_extras": extras,
            "devices_2_adj": devices_2_adj,
            "missing_device_names": missing_device_names,
            "extra_device_names": extra_device_names,
        }

    def process_section(
        self,
        device_name, section_name,
        curr_section_idx_1,
        curr_section_idx_2,
        accm_line_data,
        var_val_dict_full,
        variable_incons,
    ):
        sc = SectionComparer(general_diff_cutoff=0.12)
        (
            diff_lines,
            idx_in_ori_1st_list,
            idx_in_ori_2nd_list,
            variables,
            is_expressions,
            values,
            value_mistach_errors,
            var_val_dict,
        ) = sc.compare_sentences(
            self.outline_1.sections[curr_section_idx_1],
            self.outline_2.sections[curr_section_idx_2],
        )

        accm_line_data["diff_result"].extend(diff_lines)
        accm_line_data["variables_lines"].extend(variables)
        accm_line_data["is_expressions_lines"].extend(is_expressions)
        accm_line_data["values_lines"].extend(values)
        accm_line_data["value_mismatch_lines"].extend(value_mistach_errors)
        diff_helpers._collect_var_val_dicts(
            var_val_dict_full,
            var_val_dict,
            device_name=device_name,
            section_name=section_name,
        )
        diff_helpers._collect_var_incons(
            variable_incons=variable_incons,
            var_val_dict=var_val_dict,
            device_name=device_name,
            section_name=section_name,
        )

        # Append original line numbers
        accm_line_data["idx_in_ori_1st_all"].extend(idx_in_ori_1st_list)
        accm_line_data["idx_in_ori_2nd_all"].extend(idx_in_ori_2nd_list)

    def process_device_block_extra(
        self,
        device_merged,
        hierarchy_2,
        accm_line_data,
        struct_mismatches,
    ):
        """
        Description:
            Process a device when it is entirely extra, make annnotations.
            Modifies accm_line_data and struct_mismatches in-place.
        """
        # This means the device block is entirely extra, add tuple in diff result etc
        device_2_start, device_2_end, dvc_2_idx_in_struct = struct_helpers._find_device_start_end(
            device_merged, self.outline_2.file_struct, hierarchy_2
        )
        diff_helpers._update_m_e_device_records(
            self.outline_1,
            self.outline_2,
            accm_line_data['diff_result'],
            accm_line_data['variables_lines'],
            accm_line_data['is_expressions_lines'],
            accm_line_data['values_lines'],
            accm_line_data['value_mismatch_lines'],
            METype.E,
            device_2_start,
            device_2_end,
        )

        # Also take note in the summary. +1 because line numbers are 1-indexed
        struct_mismatches.append([BLOCK_TYPE_DEVICE, device_2_start, device_merged, ERR_TYPE_EXTRA_DEVICE])

        # Append original line numbers and -1 if not exist
        accm_line_data['idx_in_ori_1st_all'].extend([-1] * (device_2_end - device_2_start + 1))
        accm_line_data['idx_in_ori_2nd_all'].extend(range(device_2_start, device_2_end + 1))

    def process_device_block_missing(
        self,
        device_merged,
        hierarchy_1,
        accm_line_data,
        struct_mismatches,
    ):
        """
        Description:
            Process a device when it is entirely missing, make annnotations.
            Modifies accm_line_data and struct_mismatches in-place.
        """
        device_1_start, device_1_end, dvc_1_idx_in_struct = struct_helpers._find_device_start_end(
            device_merged, self.outline_1.file_struct, hierarchy_1
        )
        diff_helpers._update_m_e_device_records(
            self.outline_1,
            self.outline_2,
            accm_line_data['diff_result'],
            accm_line_data['variables_lines'],
            accm_line_data['is_expressions_lines'],
            accm_line_data['values_lines'],
            accm_line_data['value_mismatch_lines'],
            METype.M,
            device_1_start,
            device_1_end,
        )

        # Also take note in the summary. +1 because line numbers are 1-indexed
        struct_mismatches.append([BLOCK_TYPE_DEVICE, device_1_start, device_merged, ERR_TYPE_MISSING_DEVICE])

        # Append original line numbers and -1 if not exist
        accm_line_data['idx_in_ori_1st_all'].extend(range(device_1_start, device_1_end + 1))
        accm_line_data['idx_in_ori_2nd_all'].extend([-1] * (device_1_end - device_1_start + 1))

    def process_device_block_partial_missing(
        self,
        device_merged,
        hierarchy_2_adj,
        structs_data,
        curr_section_idxs,
        accm_line_data,
        struct_mismatches,
        var_val_dict_full,
        variable_incons,
    ):
        """
        Description:
            Process a device when it is partially missing / extra, make annnotations.
            Modifies accm_line_data, struct_mismatches, var_val_dict_full and variable_incons in-place.
        """
        device_2_start, device_2_end, dvc_2_idx_in_struct = struct_helpers._find_device_start_end(
            device_merged, self.outline_2.file_struct, structs_data['hierarchy_2']
        )
        device_1_start, device_1_end, dvc_1_idx_in_struct = struct_helpers._find_device_start_end(
            device_merged, self.outline_1.file_struct, structs_data['hierarchy_1']
        )
        struct_extras, struct_missings = structs_data['struct_extras'], structs_data['struct_missings']
        hierarchy_lines_1, hierarchy_lines_2 = structs_data['hierarchy_lines_1'], structs_data['hierarchy_lines_2']

        diff_helpers._update_device_title_record(
            accm_line_data,
            self.outline_2,
            device_2_start,
            msg=ERR_TYPE_ME_DEVICE,
        )
        # Append original line numbers
        accm_line_data['idx_in_ori_1st_all'].append(device_1_start)
        accm_line_data['idx_in_ori_2nd_all'].append(device_2_start)

        for section_merged in hierarchy_2_adj[device_merged]:
            # Determine if section is missing or extra beforehand, because if not do this
            # some cases might be falsely overlooked, or there will be key lookup error
            if device_merged in struct_extras and device_merged not in struct_missings:
                is_section_missing = False
                is_section_extra = section_merged in struct_extras[device_merged]
            elif device_merged not in struct_extras and device_merged in struct_missings:
                is_section_missing = section_merged in struct_missings[device_merged]
                is_section_extra = False
            else:
                is_section_missing = section_merged in struct_missings[device_merged]
                is_section_extra = section_merged in struct_extras[device_merged]

            if is_section_extra:
                # If section is in extras, it means this section is entirely extra in outline 2
                section_2_start = hierarchy_lines_2[struct_helpers._hrch_key_format(device_merged, section_merged)][0]
                section_2_end = hierarchy_lines_2[struct_helpers._hrch_key_format(device_merged, section_merged)][1]
                # Append annotations for all lines in this section
                diff_helpers._update_m_e_section_records(
                    accm_line_data,
                    METype.E,
                    section_2_start,
                    section_2_end,
                )
                struct_mismatches.append([BLOCK_TYPE_SECTION, section_2_start, section_merged, ERR_TYPE_EXTRA_SECTION])

                # Append original line numbers and -1 if not exist
                accm_line_data['idx_in_ori_1st_all'].extend([-1] * (section_2_end - section_2_start + 1))
                accm_line_data['idx_in_ori_2nd_all'].extend(range(section_2_start, section_2_end + 1))
                # Move past this section in outline 2
                curr_section_idxs[1] += 1

            elif is_section_missing:
                # Since section extra and missing are mutually exclusive, this means this section
                # is entirely missing w/r/t outline 1
                section_1_start = hierarchy_lines_1[struct_helpers._hrch_key_format(device_merged, section_merged)][0]
                section_1_end = hierarchy_lines_1[struct_helpers._hrch_key_format(device_merged, section_merged)][1]
                # Append annotations for all lines in this section
                diff_helpers._update_m_e_section_records(
                    accm_line_data,
                    METype.M,
                    section_1_start,
                    section_1_end,
                )
                struct_mismatches.append(
                    [BLOCK_TYPE_SECTION, section_1_start, section_merged, ERR_TYPE_MISSING_SECTION]
                )

                # Append original line numbers and -1 if not exist
                accm_line_data['idx_in_ori_1st_all'].extend(range(section_1_start, section_1_end + 1))
                accm_line_data['idx_in_ori_2nd_all'].extend([-1] * (section_1_end - section_1_start + 1))
                # Move past this section in outline 1
                curr_section_idxs[0] += 1

            else:
                # Otherwise, this section is present in both outlines under the same device                
                self.process_section(device_name=device_merged,
                                     section_name=section_merged,
                                     curr_section_idx_1=curr_section_idxs[0],
                                     curr_section_idx_2=curr_section_idxs[1],
                                     accm_line_data=accm_line_data,
                                     var_val_dict_full=var_val_dict_full,
                                     variable_incons=variable_incons)

                # Move past this section in outline 1 and outline 2
                curr_section_idxs[0] += 1
                curr_section_idxs[1] += 1

    def process_device_block_present(
        self,
        device_merged,
        hierarchy_1,
        hierarchy_2,
        curr_section_idxs,
        accm_line_data,
        var_val_dict_full,
        variable_incons,
    ):
        """
        Description:
            Process a device when it is completely present, make annnotations.
            Modifies accm_line_data, var_val_dict_full and variable_incons in-place.
        """
        device_2_start, device_2_end, dvc_2_idx_in_struct = struct_helpers._find_device_start_end(
            device_merged, self.outline_2.file_struct, hierarchy_2
        )
        device_1_start, device_1_end, dvc_1_idx_in_struct = struct_helpers._find_device_start_end(
            device_merged, self.outline_1.file_struct, hierarchy_1
        )
        diff_helpers._update_device_title_record(
            accm_line_data,
            self.outline_2,
            device_2_start,
            msg="equal-device-title",
        )
        # Append original line numbers
        accm_line_data['idx_in_ori_1st_all'].append(device_1_start)
        accm_line_data['idx_in_ori_2nd_all'].append(device_2_start)

        for i in range(len(hierarchy_2[device_merged])):
            self.process_section(device_name=device_merged,
                                 section_name=hierarchy_2[device_merged][i],
                                 curr_section_idx_1=curr_section_idxs[0] + i,
                                 curr_section_idx_2=curr_section_idxs[1] + i,
                                 accm_line_data=accm_line_data,
                                 var_val_dict_full=var_val_dict_full,
                                 variable_incons=variable_incons)

        # Move past all sections under this device in outline 1 and outline 2
        curr_section_idxs[0] += len(hierarchy_1[device_merged])
        curr_section_idxs[1] += len(hierarchy_2[device_merged])

    def calculate_diff(self, infra_prefixes: dict = None):
        """
        Description:
            Calculate diff deltas and auxiliary data using other classes in this program.

        Args:
            infra_prefixes (dict, optional): Infrastructure prefixes, such as fwglue and vrfglue.

        Returns:
            diff_result (list[tuple]): Diff deltas as a list of tuples. Each tuple has a specialized format.
            idx_in_ori_1st_all, idx_in_ori_2nd_all: Line numbers in original input files.
            variables_lines (list[list[str]]): Variables on all lines.
            is_expressions_lines (list[list[bool|None]]): Whether those variables are in an expression.
            values_lines (list[list[str]]): Values on all lines.
            value_mismatch_lines (list[in]): Values mismatch counts on all lines.
            ...
            correct_values: Collected mostly correct values for variables.
            variable_incons: Collected variables whose values are inconsistent with a scope.
            var_val_dict_full: Collected variable and value pairs in the whole file.
        """

        # Compare and gather hierachies in two different formats for easier lookup;
        # also gather missing/extra section names, missing/extra device names, etc.
        structs_data = self.compare_structs()

        # Merge devices/sections from both configs to form an "adjusted" hierarchy 2
        hierarchy_2_adj = {
            key: list((Counter(structs_data['hierarchy_2'].get(key, []) + structs_data['struct_missings'].get(key, []))).elements())
            for key in set(structs_data['hierarchy_2']) | set(structs_data['struct_missings'])
        }

        # Initialize data structures to store accmulated information
        accm_line_data: dict[str, list] = {
            'diff_result': [],
            'variables_lines': [],
            'is_expressions_lines': [],
            'values_lines': [],
            'value_mismatch_lines': [],
            'idx_in_ori_1st_all': [],
            'idx_in_ori_2nd_all': [],
        }
        struct_mismatches, variable_incons = [], {}
        var_val_dict_full = {}

        # Start to collect information line-by-line, while following hierachies
        curr_section_idxs = [0, 0]
        for device_merged in structs_data['devices_2_adj']:
            if device_merged in structs_data['extra_device_names']:
                # This means the device block is entirely extra, process it accordingly
                self.process_device_block_extra(
                    device_merged,
                    structs_data['hierarchy_2'],
                    accm_line_data,
                    struct_mismatches,
                )                
                # Move past all sections under this device in outline 2
                curr_section_idxs[1] += len(structs_data['hierarchy_2'][device_merged])

            elif device_merged in structs_data['missing_device_names']:
                # This means the device block is entirely missing, process it accordingly
                self.process_device_block_missing(
                    device_merged,
                    structs_data['hierarchy_1'],
                    accm_line_data,
                    struct_mismatches,
                )
                # Move past all sections under this device in outline 1
                curr_section_idxs[0] += len(structs_data['hierarchy_1'][device_merged])

            elif device_merged in structs_data['struct_extras'] or device_merged in structs_data['struct_missings']:
                # This means the device block is present in both, but partially extra and/or partially missing
                self.process_device_block_partial_missing(
                    device_merged,
                    hierarchy_2_adj,
                    structs_data,
                    curr_section_idxs,
                    accm_line_data,
                    struct_mismatches,
                    var_val_dict_full,
                    variable_incons,
                )

            else:
                # Only case left is the device block not missing/extra at all, i.e. all sections present in both
                self.process_device_block_present(
                    device_merged,
                    structs_data['hierarchy_1'],
                    structs_data['hierarchy_2'],
                    curr_section_idxs,
                    accm_line_data,
                    var_val_dict_full,
                    variable_incons,
                )

        # Collect file variablbe inconsisitencies and determine variable's correct values as well
        diff_helpers._collect_var_incons(variable_incons=variable_incons, var_val_dict=var_val_dict_full)
        correct_values = diff_helpers._determine_correct_values(var_val_dict_full, infra_prefixes=infra_prefixes)

        """ print("var_val_dict_full", var_val_dict_full)
        print("variable_incons", variable_incons)
        print("variable_incons_pretty", json.dumps(variable_incons, indent=2)json.dumps(variable_incons, indent=2))
        print(summary) """

        return (
            accm_line_data['diff_result'],
            accm_line_data['idx_in_ori_1st_all'],
            accm_line_data['idx_in_ori_2nd_all'],
            accm_line_data['variables_lines'],
            accm_line_data['is_expressions_lines'],
            accm_line_data['values_lines'],
            accm_line_data['value_mismatch_lines'],
            structs_data['hierarchy_lines_2'],
            structs_data['devices_2_adj'],
            hierarchy_2_adj,
            struct_mismatches,
            structs_data['struct_missings'],
            structs_data['struct_extras'],
            structs_data['missing_device_names'],
            structs_data['extra_device_names'],
            correct_values,
            variable_incons,
            var_val_dict_full,
        )
