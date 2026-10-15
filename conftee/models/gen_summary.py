import re, pandas, json
from typing import Union
from pandas import DataFrame

from .line_analyzer import LineAnalyzer
from .section_comparer import _evaluate_expression, _evaluate_expression_reverse
from ..utils.helpers import quick_is_section_title
from ..utils.struct_helpers import _hrch_key_format
from ..utils.diff_helpers import _lookup_correct_values, _value_is_wrong_sourced, _value_is_wrong_link

from ..utils.constants import GENERAL_IPV4_REGEX
from ..utils import schema as schema_module
from ..models.section_comparer import (
    COL_LABEL_LINE_NUM_1,
    COL_LABEL_LINE_NUM_2,
    ERR_TYPE_MISSING_LINE,
    ERR_TYPE_EXTRA_LINE,
)
from ..utils.diff_helpers import (
    _consistency_scopes,
    LNK_RELATIONS,
    ERR_TYPE_MISSING_DEVICE,
    ERR_TYPE_EXTRA_DEVICE,
    ERR_TYPE_MISSING_SECTION,
    ERR_TYPE_EXTRA_SECTION,
)

COL_LABEL_LINE_CNTT_1, COL_LABEL_LINE_CNTT_2, COL_LABEL_VAL_MISMATCH, COL_LABEL_DIFF_RESULT = (
    "Line in 1",
    "Line in 2",
    "Value mistaches",
    "diff_result",
)
COL_LABEL_VARS, COL_LABEL_EXPRS, COL_LABEL_VALS = "variables", "is expression", "values"
ERR_TYPE_VAL_MISMATCH, ERR_TYPE_VAL_INCONS_SCT, ERR_TYPE_VAL_INCONS_FILE, ERR_TYPE_VAL_WRONG_SRC, ERR_TYPE_VAL_WRONG_LNK, ERR_TYPE_CMD_MISMATCH = (
    "value-mistach",
    "value-incons-section",
    "value-incons",
    "value-wrong-src",
    "value-wrong-link",
    "command-mistach",
)

# Used to be for Jinja2 powered html output
OUTPUT_DIR = '/html_output/'
JINJA_TEMPLATE_DIR = '/html_templates/'

def _line_is_empty(line:str):
    empty_pattern = r'^[\s\n!]+$'
    return bool(re.match(empty_pattern, line)) or len(line) <= 0

def _line_is_extra(row):
    """
    Determine if a line is present in user but not in golden. Used by _make_line_report(.).
    """
    return row[COL_LABEL_LINE_NUM_1] == -1

def _line_is_missing(row):
    """
    Determine if a line is present in golden but not in user. Used by _make_line_report(.).
    """
    # Suppress the missing alert if golden lines is a comment line
    if len(row[COL_LABEL_LINE_CNTT_1]) >=1:
        is_comment_g = row[COL_LABEL_LINE_CNTT_1][0] == "!"
    else:
        is_comment_g = False
    
    return row[COL_LABEL_LINE_NUM_2] == -1 and not is_comment_g

def _is_missing_extra(row):
    """
    Determine if a line is missing or extra, ignoring empty lines. Used in generating the summary counts list.
    """
    is_line_1_empty = _line_is_empty(row[COL_LABEL_LINE_CNTT_1])
    is_line_2_empty = _line_is_empty(row[COL_LABEL_LINE_CNTT_2])
    return (_line_is_extra(row) and not is_line_2_empty) or (_line_is_missing(row) and not is_line_1_empty)

def _make_line_report(row, correct_values: dict, variable_incons: dict, var_val_dict_full: dict, device_name: str, section_name: str, schema=None):
    """
    Description:
        Row data processing function applied to a result Dataframe in specific format.
        This is another load bearing function for json report generation besides the create_summary_json(.)
    """
    schema = schema if schema is not None else schema_module.default()
    var_cons_section, _ = _consistency_scopes(schema)

    is_line_1_empty = _line_is_empty(row[COL_LABEL_LINE_CNTT_1])
    is_line_2_empty = _line_is_empty(row[COL_LABEL_LINE_CNTT_2])

    if _line_is_missing(row) and not is_line_1_empty:
        # If the diff delta indicates missing line, return missing line msg as report
        expected = row[COL_LABEL_LINE_CNTT_1] if len(row[COL_LABEL_LINE_CNTT_1]) > 0 else "\n"
        return [ERR_TYPE_MISSING_LINE, {"expected": expected, "actual": "", "line": row[COL_LABEL_LINE_NUM_1]}]

    if _line_is_extra(row) and not is_line_2_empty:
        # If the diff delta indicates extra line, same
        actual = row[COL_LABEL_LINE_CNTT_2] if len(row[COL_LABEL_LINE_CNTT_2]) > 0 else "\n"
        return [ERR_TYPE_EXTRA_LINE, {"expected": "", "actual": actual, "line": row[COL_LABEL_LINE_NUM_2]}]

    # If not entirely missing/extra, then inspect detailed in-line errors by collecting
    # error types and constructing expected line content
    err_type_msg: list[str] = []
    actual = row[COL_LABEL_LINE_CNTT_2]
    expected = ""
    vars, exprs, vals = row[COL_LABEL_VARS], row[COL_LABEL_EXPRS], row[COL_LABEL_VALS]
    mismatched_vars, mismatched_vals, mismatched_corrections = [], [], []
    wrong_sourced_vars, wrong_sourced_vals, wrong_sourced_types, wrong_sourced_corrections = [], [], [], []
    incons_vars, incons_vals, incons_types, incons_corrections = [], [], [], []
    wrong_link_vars, wrong_link_vals, wrong_link_types, wrong_link_corrections = [], [], [], []
    mismatched_cmd = 0

    la = LineAnalyzer(schema)
    for i in range(len(vars)):
        # First determine if vars[i] is an atomic variable or an expression
        if exprs[i] is False:
            # This means it is just an atomic variable. No more needs to be done.
            var_i = vars[i]
            val_i = vals[i]
        else:
            # This means this is an expression.
            var_i = exprs[i][1:-1]
            val_i = _evaluate_expression_reverse(vars[i], var_i, vals[i], schema=schema)

        # Reminder: From here on, vals[i] is the value for a variable or expression, but val_i is definately
        # value for a variable; so check format mismatches using vals[i], but check inconsistencies etc using val_i.

        # Look up correct values collected beforehand, so that various inner checks inside the if-blocks can use it at will
        correct_val, consistency_type = _lookup_correct_values(var_i, correct_values, device_name, section_name, schema=schema)
        if la.variable_is_value_match(var_i, vals[i]):
            # Only check value source and consistency if it has correct format, because otherwise these would be meaningless

            # Check if it is wrong sourced
            is_wrong_sourced, wrong_source_type, correct_source = _value_is_wrong_sourced(var_i, val_i, correct_values, section_name)
            if is_wrong_sourced:
                wrong_sourced_vars.append(var_i)
                if exprs[i]:
                    # Append the value for the expression if this is an expression to clear things up a bit
                    wrong_sourced_vals.append(val_i + f' ({vals[i]} for {{{vars[i]}}})')
                else:
                    wrong_sourced_vals.append(val_i)
                wrong_sourced_types.append(wrong_source_type)
                wrong_sourced_corrections.append(correct_source)

            # Check if it is inconsistent with the first most frequent value
            if var_i in variable_incons:
                if val_i != correct_val:
                    # Reminder: have to deal with expressions seperately to avoid explanation confusion
                    incons_vars.append(var_i) if exprs[i] is False else incons_vars.append(vars[i])
                    incons_vals.append(val_i) if exprs[i] is False else incons_vals.append(vals[i])
                    (
                        incons_types.append(ERR_TYPE_VAL_INCONS_SCT)
                        if consistency_type == 1
                        else incons_types.append(ERR_TYPE_VAL_INCONS_FILE)
                    )
                    (
                        incons_corrections.append(correct_val)
                        if exprs[i] is False
                        else incons_corrections.append(
                            _evaluate_expression(expression=vars[i], variable=var_i, var_value=correct_val, schema=schema)
                        )
                    )

            # Check if it is a corret value based on "link" relations, if applicable
            if var_i in LNK_RELATIONS.keys():
                is_wrong_link, wrong_link_type, correct_link_val = _value_is_wrong_link(var_i, val_i, correct_values, var_val_dict_full, section_name)
                if is_wrong_link:
                    wrong_link_vars.append(var_i)
                    wrong_link_vals.append(val_i)
                    wrong_link_types.append(wrong_link_type)
                    wrong_link_corrections.append(correct_link_val)

        else:
            mismatched_vars.append(var_i)
            # Currently missing values are also counted as value mismatches so better annotate that differently
            mismatched_vals.append(vals[i]) if vals[i] else mismatched_vals.append("-1")
            if correct_val[0] == "{":
                # This means no valid value recorded (refer to the code of _determine_correct_values(.)).
                # Mark it for the explanations we have to construct later
                mismatched_corrections.append("-1")
            else:
                mismatched_corrections.append(correct_val)

    # Inspect command part of this line by reading info from the diff deltas column
    mismatched_cmd = _count_mismatched_cmd(row) if not (is_line_1_empty or is_line_2_empty) else 0

    if int(row[COL_LABEL_VAL_MISMATCH]) >= 1:
        err_type_msg.append(ERR_TYPE_VAL_MISMATCH)

    if len(wrong_sourced_vars) > 0:
        err_type_msg.append(ERR_TYPE_VAL_WRONG_SRC)

    if len(incons_vars) > 0:
        err_type_msg.append(ERR_TYPE_VAL_INCONS_FILE)

    if len(wrong_link_vars) > 0:
        err_type_msg.append(ERR_TYPE_VAL_WRONG_LNK)

    if mismatched_cmd > 0:
        err_type_msg.append(ERR_TYPE_CMD_MISMATCH)

    if len(err_type_msg) > 0:
        # If there are any in-line errors, e.g. value mismatch or wrong source, use diff deltas to report
        # Currently this also means there is at least one tuple with 'replace-var' or 'replace-var-err'
        line_1 = row[COL_LABEL_LINE_CNTT_1]
        line_diff = row[COL_LABEL_DIFF_RESULT]

        var_idx = 0
        for d_tuple in line_diff:
            if (d_tuple[0] == "replace-var") or (d_tuple[0] == "replace-var-err"):
                # This means there is a variable represented by the tuple. Look it up in the var array collected by LineAnalyser before.

                # First determine if vars[var_idx] is an atomic variable or an expression
                var: str = vars[var_idx] if exprs[var_idx] is False else exprs[var_idx][1:-1]
                try:
                    # If variable has wrong sourced value, use variable correct source as correct value here
                    wrong_sourced_var_idx = wrong_sourced_vars.index(var)
                    correct_val = "<" + " - ".join(wrong_sourced_corrections[wrong_sourced_var_idx]) + ">"
                except ValueError:
                    # If var is not in wrong_sourced_vars (ValueError), meaning we can check consistency
                    if var in var_cons_section:
                        correct_val = correct_values[var][device_name][section_name]
                    else:
                        correct_val = correct_values[var]

                    # But, if variable has an relation and its relation is wrong, overwrite the correct_value with correct linked value
                    if var in LNK_RELATIONS.keys() and var in wrong_link_vars:
                        wrong_link_var_idx = wrong_link_vars.index(var)
                        correct_val = wrong_link_corrections[wrong_link_var_idx]

                # Then use correct value to construct expected line
                if exprs[var_idx] is False:
                    expected = expected.rstrip() + " " + correct_val
                else:
                    # Adjust the correct value based on whether it is an IPv4 address or not
                    correct_val_is_ipv4 = bool(re.fullmatch(GENERAL_IPV4_REGEX, correct_val))
                    correct_val_adj = _evaluate_expression(vars[var_idx], var, correct_val, schema=schema) if correct_val_is_ipv4 else correct_val
                    expected = expected.rstrip() + " " + correct_val_adj

                # We trust the LineAnalyzer to have collected corresponding var-val pairs correctly, so var[var_idx]
                # should be within the line's range and var_idx should be valid in both vars and vals.
                # Finally increment counter because "consumed" one variable.
                var_idx += 1

            elif d_tuple[0] == COL_LABEL_LINE_NUM_1:
                # Some line diff have line num 1 appended, ignore that type of tuples
                pass

            else:
                # All other cases, 'equal', 'insert', 'delete' and 'replace' can be treated as one case
                expected += line_1[d_tuple[1] : d_tuple[2]]

        # Then append explanations
        explanations = []

        # Explanation for mismatched values, if any
        for i in range(len(mismatched_vars)):
            correction = (
                f"; luckily we know {mismatched_corrections[i]} for it from other places"
                if mismatched_corrections[i] != "-1"
                else "; unfortunately there is no known valid value for it"
            )

            if mismatched_vals[i] != "-1":
                explanations.append(f"{mismatched_vals[i]} for {{{mismatched_vars[i]}}} mismatches the format" + correction)
            else:                
                explanations.append(f"Missing a value for {{{mismatched_vars[i]}}}" + correction)

        # Explanation for wrong sourced values, if any
        for i in range(len(wrong_sourced_vars)):
            correction = " - ".join(wrong_sourced_corrections[i])
            explanations.append(
                f"{wrong_sourced_vals[i]} for {{{wrong_sourced_vars[i]}}} is not in expected range ({wrong_sourced_types[i]}): {correction}"
            )

        # Explanation for inconsistent values, if any
        for i in range(len(incons_vars)):
            explanations.append(
                f"{incons_vals[i]} for {{{incons_vars[i]}}} is inconsistent with {incons_corrections[i]} ({incons_types[i]}), at least one of them is wrong"
            )

        # Explanation for wrong relations, if any
        for i in range(len(wrong_link_vars)):
            explanations.append(
                f"{wrong_link_vals[i]} for {{{wrong_link_vars[i]}}} is not inherited from {wrong_link_corrections[i]} ({wrong_link_types[i]})"
            )

        # Explanation for mismatched commands, if any
        if mismatched_cmd > 0:
            explanations.append(
                f"The command part differs from that in the golden line at {mismatched_cmd} places"
            )

        return [
            ", ".join(err_type_msg),
            {"expected": expected, "actual": actual, "explanations": explanations, "line": row[COL_LABEL_LINE_NUM_2]},
        ]


def _count_mismatched_cmd(row):
    """
    Helper function to count differences in non-variable words in a row.

    Note: This function is only called when a line is not missing nor extra. So if that prerequisite changes, this function has to keep up.
    """
    if not isinstance(row[COL_LABEL_DIFF_RESULT], list):
        # If diff deltas is not a list, then this is in a missing device or section, so skip
        return 0
    
    if quick_is_section_title(line=row[COL_LABEL_LINE_CNTT_2]):
        # If line 2 content is a likely a section title, also skip
        return 0

    count = 0
    for delta in row[COL_LABEL_DIFF_RESULT]:
        if delta[0] in ["insert", "delete"]:
            count += 1
        elif delta[0] == "replace":
            # When there are IPv4 variables and values, LineAnalyzer "mask" them and force them to be different no matter what,
            # so need to deal with replace specially here, by comparing the un-"masked" substrings again.
            if row[COL_LABEL_LINE_CNTT_1][delta[1] : delta[2]] != row[COL_LABEL_LINE_CNTT_2][delta[3] : delta[4]]:
                count += 1
    
    return count

def _append_summ_to_df(diff_result_df, summary):
    summary_message = "There are " + ", ".join([" ".join(map(str, child_list)) for child_list in summary])
    diff_result_df.loc[len(diff_result_df)] = {
        COL_LABEL_LINE_NUM_1: -1,
        COL_LABEL_LINE_CNTT_1: summary_message,
        COL_LABEL_LINE_NUM_2: None,
        COL_LABEL_LINE_CNTT_2: None,
        COL_LABEL_VARS: None,
        COL_LABEL_EXPRS: None,
        COL_LABEL_VALS: None,
        COL_LABEL_VAL_MISMATCH: None,
    }


class GenSummary:

    def create_summary_dataframe(
        self,
        outline_1,
        outline_2,
        diff_result: list[tuple],
        idx_list_1: list[int],
        idx_list_2: list[int],
        variables_lines,
        is_expressions_lines,
        values_lines,
        value_mismatch_lines,
    ):
        """
        Description:
            Compile all raw info collected by the classes into a dataframe.
        """

        diff_result_df = pandas.DataFrame(
            {
                COL_LABEL_LINE_NUM_1: idx_list_1,
                COL_LABEL_LINE_NUM_2: idx_list_2,
                COL_LABEL_DIFF_RESULT: diff_result,
                COL_LABEL_VARS: variables_lines,
                COL_LABEL_EXPRS: is_expressions_lines,
                COL_LABEL_VALS: values_lines,
                COL_LABEL_VAL_MISMATCH: value_mismatch_lines,
            }
        )

        # Insert line contents from golden config; loc=1 because loc=0 is the column 'Line num 1' currently
        diff_result_df.insert(
            loc=1,
            column=COL_LABEL_LINE_CNTT_1,
            value=diff_result_df[COL_LABEL_LINE_NUM_1].apply(
                lambda val: outline_1.file_content[val - 1].rstrip("\n") if val != -1 else ""
            ),
        )

        # Insert line contents from golden config; loc=1 because loc=0 is the column 'Line num 2' now
        diff_result_df.insert(
            loc=3,
            column=COL_LABEL_LINE_CNTT_2,
            value=diff_result_df[COL_LABEL_LINE_NUM_2].apply(
                lambda val: outline_2.file_content[val - 1].rstrip("\n") if val != -1 else ""
            ),
        )

        return diff_result_df

    def create_summary_list(
        self,
        value_mismatch_lines: list[int],
        struct_mismatches: list[list[str]],
        variable_incons: dict[str, list],
        correct_values: dict[str, str],
        diff_result_df: DataFrame,
        schema=None,
    ):
        value_mismatch_cnt = sum(value_mismatch_lines)
        struct_mismatch_cnt = len(struct_mismatches)
        value_incons_cnt = 0

        schema = schema if schema is not None else schema_module.default()

        # Count variable inconsistency errors
        la = LineAnalyzer(schema)
        for var in variable_incons:
            for val_on_line in variable_incons[var]:
                device_name, section_name = val_on_line[2], val_on_line[3]
                if la.variable_is_value_match(var, val_on_line[0]):
                    # Same rule as in the create_summary_json(.):
                    # If a value has correct format, has correct source, but is not the same as the overall correct value, then count as inconsistent
                    is_wrong_sourced, _, _ = _value_is_wrong_sourced(var, val_on_line[0], correct_values, section_name)
                    correct_val, _ = _lookup_correct_values(var, correct_values, device_name, section_name, schema=schema)
                    if not is_wrong_sourced and correct_val[0] != "{" and val_on_line[0] != correct_val:
                        value_incons_cnt += 1

        # Count missing/extra line errors
        lines_m_e_series = diff_result_df.apply(lambda row: _is_missing_extra(row), axis=1)
        lines_m_e_cnt = lines_m_e_series.sum()

        # Count command mismatch errors
        mismatched_cmd_series = diff_result_df.apply(lambda row: _count_mismatched_cmd(row), axis=1)
        mismatched_cmd_cnt = (mismatched_cmd_series > 0).sum()

        return [
            [value_mismatch_cnt, "value mismatches"],
            [struct_mismatch_cnt, "struct mismatches"],
            [value_incons_cnt, "value inconsistencies"],
            [lines_m_e_cnt, "missed or extra lines"],
            [mismatched_cmd_cnt, "command mismatches"],
        ]

    def create_summary_json(
        self,
        hierarchy_lines_2: dict,
        devices_2_adj: list[str],
        hierarchy_2_adj: dict,
        struct_missings: dict,
        struct_extras: dict,
        missing_device_names: list,
        extra_device_names: list,
        correct_values: dict,
        variable_incons: dict,
        var_val_dict_full: dict[str, list[list[Union[str, int]]]],
        diff_result_df: pandas.DataFrame,
        schema=None,
    ):
        """
        Description:
            Construct full report for integration testing, in designated format.
        """
        result = {}

        # Add missing/extra blocks, ms/ex lines, and value mismatches into report
        for device_merged in devices_2_adj:
            result[device_merged] = {}

            if device_merged in extra_device_names:
                # Entire device is extra, only exists in hierarchy_2
                result[device_merged][ERR_TYPE_EXTRA_DEVICE] = "this"

            elif device_merged in missing_device_names:
                # Entire device is missing, only exists in hierarchy_1
                result[device_merged][ERR_TYPE_MISSING_DEVICE] = "this"

            elif device_merged in struct_missings or device_merged in struct_extras:
                # Device has missing and/or extra sections, exists in both hierarchy_1 and 2
                for section_merged in hierarchy_2_adj[device_merged]:
                    # Determine if section is missing or extra beforehand, because if not do this
                    # some cases might be falsely overlooked, or there will be key lookup error
                    if (
                        device_merged in struct_extras
                        and device_merged not in struct_missings
                    ):
                        is_section_missing = False
                        is_section_extra = (
                            section_merged in struct_extras[device_merged]
                        )
                    elif (
                        device_merged not in struct_extras
                        and device_merged in struct_missings
                    ):
                        is_section_missing = (
                            section_merged in struct_missings[device_merged]
                        )
                        is_section_extra = False
                    else:
                        is_section_missing = (
                            section_merged in struct_missings[device_merged]
                        )
                        is_section_extra = (
                            section_merged in struct_extras[device_merged]
                        )

                    result[device_merged][section_merged] = []
                    if is_section_extra:
                        # Entire section is extra
                        result[device_merged][section_merged].append(ERR_TYPE_EXTRA_SECTION)
                    elif is_section_missing:
                        # Entire section is missing
                        result[device_merged][section_merged].append(ERR_TYPE_MISSING_SECTION)
                    else:
                        # Section exists in both hierarchy_1 and 2
                        # Get the start and end in the user config for this section
                        section_key_in_hrch_lines = _hrch_key_format(
                            device_merged, section_merged
                        )
                        section_2_start, section_2_end = (
                            hierarchy_lines_2[section_key_in_hrch_lines][0],
                            hierarchy_lines_2[section_key_in_hrch_lines][1],
                        )
                        # Get the row indices in the dataframe for this section, should be the same for golden and user
                        section_start_in_df = diff_result_df[
                            diff_result_df[COL_LABEL_LINE_NUM_2] == section_2_start
                        ].index[0]
                        section_end_in_df = diff_result_df[
                            diff_result_df[COL_LABEL_LINE_NUM_2] == section_2_end
                        ].index[0]
                        section_slice = diff_result_df[
                            (diff_result_df.index >= section_start_in_df)
                            & (diff_result_df.index <= section_end_in_df)
                        ]

                        section_line_reports = section_slice.apply(
                            lambda row: _make_line_report(
                                row,
                                correct_values,
                                variable_incons,
                                var_val_dict_full,
                                device_merged,
                                section_merged,
                                schema,
                            ),
                            axis=1,
                        )
                        result[device_merged][section_merged].extend(
                            section_line_reports.dropna().to_list()
                        )

            else:
                # Device has no missing nor extra sections, exists in both hierarchy_1 and 2

                for section_merged in hierarchy_2_adj[device_merged]:
                    # Section exists in both hierarchy_1 and 2 due to outer else
                    # Get the start and end in the user config for this section
                    section_key_in_hrch_lines = _hrch_key_format(
                        device_merged, section_merged
                    )
                    section_2_start, section_2_end = (
                        hierarchy_lines_2[section_key_in_hrch_lines][0],
                        hierarchy_lines_2[section_key_in_hrch_lines][1],
                    )
                    # Get the row indices in the dataframe for this section, should be the same for golden and user
                    section_start_in_df = diff_result_df[
                        diff_result_df[COL_LABEL_LINE_NUM_2] == section_2_start
                    ].index[0]
                    section_end_in_df = diff_result_df[
                        diff_result_df[COL_LABEL_LINE_NUM_2] == section_2_end
                    ].index[0]

                    section_slice = diff_result_df[
                        (diff_result_df.index >= section_start_in_df)
                        & (diff_result_df.index <= section_end_in_df)
                    ]

                    result[device_merged][section_merged] = []
                    section_line_reports = section_slice.apply(
                        lambda row: _make_line_report(
                            row,
                            correct_values,
                            variable_incons,
                            var_val_dict_full,
                            device_merged,
                            section_merged,
                            schema,
                        ),
                        axis=1,
                    )
                    result[device_merged][section_merged].extend(
                        section_line_reports.dropna().to_list()
                    )

        return json.dumps(result, indent=2)

    def generate_reports(self, outline_1, outline_2, comparer_results):

        # Unpack results passed from a ConfigDiffHandler's calculate_diff()
        # There are a lot! So be sure to change and double check this part when that one changes.
        (
            diff_result,
            idx_in_ori_1st_all,
            idx_in_ori_2nd_all,
            variables_lines,
            is_expressions_lines,
            values_lines,
            value_mismatch_lines,
            hierarchy_lines_2,
            devices_2_adj,
            hierarchy_2_adj,
            struct_mismatches,
            struct_missings,
            struct_extras,
            missing_device_names,
            extra_device_names,
            correct_values,
            variable_incons,
            var_val_dict_full,
        ) = comparer_results

        diff_result_df = self.create_summary_dataframe(
            outline_1,
            outline_2,
            diff_result,
            idx_in_ori_1st_all,
            idx_in_ori_2nd_all,
            variables_lines,
            is_expressions_lines,
            values_lines,
            value_mismatch_lines,
        )

        # Using the above two piece of info, get a summary of error type counts, for quick checking
        summary = self.create_summary_list(
            value_mismatch_lines, struct_mismatches, variable_incons, correct_values, diff_result_df
        )
        _append_summ_to_df(diff_result_df, summary)

        # Finally use everything above, postprocess them and assemble errors into a JSON report
        json_report = self.create_summary_json(
            hierarchy_lines_2,
            devices_2_adj,
            hierarchy_2_adj,
            struct_missings,
            struct_extras,
            missing_device_names,
            extra_device_names,
            correct_values,
            variable_incons,
            var_val_dict_full,
            diff_result_df,
        )

        return summary, diff_result_df, json_report

    def _generate_html(self, output_file_name:str=""):
        """
        Description:
            (!!!The html visulization is currently broken and not in use because of both requirement changes and implementation changes.)
            Read a Jinja template and render the diff check result into an html format string. And if needed, write to a local file.
            
        Args:
            output_file_name (str): The file name of output local html file. Defaults to "", meaning no local file will be written.
        
        Returns:
            str: Generated html format string.
        """

        """ diff_result = self.calculate_diff()
        # Setup Jinja2 environment
        path = pathlib.Path(__file__)
        parent_path = path.parent.parent
        env = Environment(loader=FileSystemLoader(str(parent_path)+JINJA_TEMPLATE_DIR))
        
        # Load the template
        template = env.get_template('main_diff_check.html')
        
        # Render the template with the diff_result
        rendered_html = template.render(diff_result=diff_result,
                                        file_content_1=self.outline_1.sections[0].content, file_struct_1=self.outline_1.file_struct,
                                        file_content_2=self.outline_2.sections[0].content, file_struct_2=self.outline_2.file_struct)
        
        # If a non-empty output file name is specified, write html to file
        if output_file_name:
            print(f"Writing html to local storage with name \"{output_file_name}\"...")
            filename = output_file_name
            filepath = OUTPUT_DIR
            # Write the rendered content to an HTML file
            file_name_and_path = str(parent_path) + filepath + filename
            with open(file_name_and_path, 'w') as file:
                file.write(rendered_html)
        
        return rendered_html """
