import re, pandas

from .section import Section
from .differ_o import DifferO
from .line_analyzer import LineAnalyzer
from ..utils.helpers import string_to_int_safe, reverse_operator, calc_ipv4_algebra, calc_ints_string_op

from .differ_o import (
    COL_LABEL_OPS, COL_LABEL_LINE_CONTENT,
    COL_LABEL_LINE_NUM_1, COL_LABEL_LINE_NUM_2,
    COL_LABEL_LINE_TAG,
)
from .differ_o import (
    TAG_REMOVE_FROM_1ST, TAG_REMOVE_FROM_2ND,
    TAG_CHANGE_BOTH, TAG_CHANGE_1ST, TAG_CHANGE_2ND,
    TAG_IDENTICAL,
)
from ..utils.constants import IPV4_VARIABLES, INT_VARIABLES

OPERATION_REGEX = r"\}[+-]([1-9][0-9]?|[0-9])"
ERR_TYPE_MISSING_LINE, ERR_TYPE_EXTRA_LINE = "missing-line", "extra-line"


## Helper functions related to SectionComparer
def _evaluate_expression(expression: str, variable: str, var_value: str, _reverse: bool = False):
    """
    Description:
        Helper function to read simple algebraic operation from a string and calculate result.
        Currently only support IPv4 and int, "+" and "-"; and the OPERATION_REGEX only detects
        operands up to 2 digits (from 0 to 99).

    Args:
        expression (str): The string containing the expression. Must be in specific format.
        variable (str): The string containing the variable's name, no brackets. Should be in the expression string.
        value (str): A value corresponding to the variable. Should be in the format required by the variable.
        _reverse (bool, Optional): Whether the operator should be "reversed". Intended for internal use.

    Returns:
        str | int | None: Currently either an IPv4 address string or an int. Return empty string if fails.
    Examples:
        Input "{{Vrfglue_prefix}-1}", "Vrfglue_prefix", "173.14.143.10" will give:
            173.14.143.9
        Input "{{Vlan_ID_user}+17}", "Vlan_ID_user", "245" will give:
            262
    """
    result = ""
    op_str = re.search(OPERATION_REGEX, expression)[0]
    if not op_str:
        return result

    # The char after the } should be the operator. "Reverse" it if the caller needs that.
    operator = op_str[1] if not _reverse else reverse_operator(op_str[1])
    # The rest of a valid match will be a string containing only 0-99
    operand = int(op_str[2:])
    if variable in IPV4_VARIABLES:
        # This means the variable should have an IPv4 address value
        result = calc_ipv4_algebra(ip=var_value, operator=operator, operand=operand)
    elif variable in INT_VARIABLES:
        # This means the variable should have an integer value
        value_int = string_to_int_safe(var_value)
        if value_int:
            result = calc_ints_string_op(operand1=value_int, operator=operator, operand2=operand)
    else:
        raise ValueError(
            f"[_evaluate_expression()] Variable {variable} is in an expression but there is no valid algebra operation for it.\nFix code or double check the variable name?"
        )

    return result


def _evaluate_expression_reverse(expression: str, variable: str, expr_value: str):
    """
    Description:
        Helper function that solves variable's value from an expression's value. "Reverse" whatever operators
        the _evaluate_expression(.) supports. So it is also a wrapper upon that helper function.
    """
    return _evaluate_expression(expression, variable, expr_value, _reverse=True)


## Class start
class SectionComparer:

    def __init__(self, general_diff_cutoff: float):
        """
        Description:
            Instantialize. This class handles comparison at the section (list of sentences) level.

        Args:
            general_diff_cutoff (float): General line similarity (not excluding variables) cutoff for a DifferO to use. Meaning a line pair with similarity > this value will be compared in depth; < this value will be seen as missing/extra.
        """
        self.line_analyzer = LineAnalyzer()
        self.general_cutoff = general_diff_cutoff

    def _flush_by_1(self, list: list[int], start_idx: int, end_idx: int, skip_value: int = -1):
        """
        Description:
            Simple function to add 1 to every integer in a range in the list[int].

        Args:
            list (list[int]): The list of integers to be changed.
            start_idx (int): Index of range start.
            end_idx (int): Index of range end.
            skip_value (int): Value to be skipped, defaults to -1. Because dataframe in this program uses -1 to indicate invalid line number.

        Returns:
            None. Changes are made in-place.

        Examples:
            _flush_by_1([3, 9, -1, 12, 13], 2, 4, -1) returns [3, 9, -1, 13, 14]
        """
        for i in range(start_idx, end_idx):
            if list[i] != skip_value:
                list[i] += 1

    def _adjust_line_nums(
        self, df: pandas.DataFrame, col_1: str, col_2: str, col_line_tag: str
    ) -> tuple[list[int], list[int], list[str]]:
        """
        Description:
            Adjust line numbers in both paragraphs based on missings and extras.

        Args:
            df (pandas.DataFrame): The dataframe containing all diff delta information.
            col_1 (str): Name of the column storing line numbers in paragraph1.
            col_2 (str): Name of the column storing line numbers in paragraph2.
            col_line_tag (str): Name of the column storing line change tags.

        Returns:
            list[int]: Adjusted line numbers for paragraph1.
            list[int]: Adjusted line numbers for paragraph2.
            list[str]: Filtered line change tags.

        Examples:
            for dataframe:
            | ... | Line num 1 | Line num 2 | line tag |
            |-----|------------|------------|----------|
            | ... | 1          | -1         | chg_both |
            | ... | -1         | -1         | chg_both |
            | ... | -1         | 1          | chg_both |
            | ... | -1         | -1         | chg_both |
            | ... | 2          | 2          | same     |
            | ... | 3          | -1         | extra_1  |
            | ... | 4          | -1         | chg_2    |
            | ... | -1         | 3          | chg_2    |
            | ... | -1         | -1         | chg_2    |
            | ... | 5          | -1         | chg_1    |
            | ... | -1         | -1         | chg_1    |
            | ... | -1         | 4          | chg_1    |
            |     | -1         | 5          | extra_2  |
            _adjust_line_nums(df, 'Line num 1', 'Line num 2', 'Line tag') returns
                [1, 2, 3, 4, 5, -1], [1, 2, -1, 4, 5, 6], ['chg_both', 'same', 'extra_1', 'chg_2', 'chg_1', 'extra_2']
        """
        extract1, extract2, tags = [], [], []
        row_count = df.shape[0]

        row_idx = 0
        while row_idx < row_count:
            # In this scenario row lable always equal row index
            line_num1 = df.loc[row_idx, col_1]
            line_num2 = df.loc[row_idx, col_2]
            tag = df.loc[row_idx, col_line_tag]
            if tag == TAG_IDENTICAL or tag == TAG_REMOVE_FROM_1ST or tag == TAG_REMOVE_FROM_2ND:
                extract1.append(line_num1)
                extract2.append(line_num2)
                tags.append(tag)
                row_idx += 1
            elif tag == TAG_CHANGE_BOTH or tag == TAG_CHANGE_1ST:
                extract1.append(line_num1)
                extract2.append(df.loc[row_idx + 2, col_2])
                tags.append(tag)
                if tag == TAG_CHANGE_BOTH:
                    row_idx += 4
                else:
                    row_idx += 3
            elif tag == TAG_CHANGE_2ND:
                extract1.append(line_num1)
                extract2.append(df.loc[row_idx + 1, col_2])
                tags.append(tag)
                row_idx += 3
            else:
                continue

        if len(extract1) != len(extract2):
            raise ValueError("[Section comparer] Extracted line nums 1 and line nums 2 length not equal")

        for i in range(len(extract1)):
            if tags[i] == TAG_REMOVE_FROM_1ST:
                self._flush_by_1(extract2, i + 1, len(extract2))
            elif tags[i] == TAG_REMOVE_FROM_2ND:
                self._flush_by_1(extract1, i + 1, len(extract1))
            else:
                continue

        return extract1, extract2, tags

    def inspect_lines(self, section1: Section, section2: Section):
        # Some trivial cases. If the 2 sections are not of the correct type, raise error
        if not section1.is_golden:
            raise ValueError(
                "[Section comparer] Cannot check extra lines in a section if the first input is not a section from golden config."
            )
        if section2.is_golden:
            raise ValueError(
                "[Section comparer] Cannot check extra lines in a section if both inputs are sections from golden config."
            )

        # From here on it is certain section1 is golden and section2 is not golden
        missing_lines: list[int] = []
        extra_lines: list[int] = []

        # If section1 is golden but empty, we know the whole section2 is extra
        if section1.is_empty():
            for i in range(section2.line_numbers[0], section2.line_numbers[1] + 1):
                extra_lines.append(i)

            lines_nums_2 = list(range(section2.line_numbers[0], section2.line_numbers[1] + 1))
            return missing_lines, extra_lines, [-1], lines_nums_2

        # If section1 is golden and non-empty, but section2 is empty, we know the whole section2 is missing
        if not section1.is_empty() and section2.is_empty():
            for i in range(section1.line_numbers[0], section1.line_numbers[1] + 1):
                missing_lines.append(i)

            lines_nums_1 = list(range(section1.line_numbers[0], section1.line_numbers[1] + 1))
            return missing_lines, extra_lines, lines_nums_1, [-1]

        # Otherwise, neither is empty, compare them line by line. Use the augmented DifferO class.
        differ_o = DifferO(cutoff=self.general_cutoff)
        comp_res = differ_o.compare(section1.content, section2.content)
        df, blocks, missing_lines_tmp, extra_lines_tmp = differ_o.seperate_line_ops(comp_res)
        # And append them to the to-be-returned variables
        missing_lines.extend(missing_lines_tmp)
        extra_lines.extend(extra_lines_tmp)
        # Shift all line numbers by their section start number
        df.loc[df[COL_LABEL_LINE_NUM_1] > -1, COL_LABEL_LINE_NUM_1] += section1.start_line - 1
        df.loc[df[COL_LABEL_LINE_NUM_2] > -1, COL_LABEL_LINE_NUM_2] += section2.start_line - 1

        adj_lines_1st, adj_lines_2nd, _ = self._adjust_line_nums(
            df, COL_LABEL_LINE_NUM_1, COL_LABEL_LINE_NUM_2, COL_LABEL_LINE_TAG
        )

        return missing_lines, extra_lines, adj_lines_1st, adj_lines_2nd

    def _collect_line_var_val(
        self, result, vars_line: list[str], is_exprs_line: list, vals_line: list[str], val_line_num: int
    ):
        for i in range(len(vars_line)):
            # First determine if vars[i] is an atomic variable or an expression
            if is_exprs_line[i] is False:
                # This means it is just an atomic variable. No more needs to be done.
                var = vars_line[i]
                val = vals_line[i]
            else:
                # This means this is an expression.
                # In this case the variable is recorded at is_exprs_line[i] with brakets.
                var = is_exprs_line[i][1:-1]
                # And its value needs to be calculated.
                val = _evaluate_expression_reverse(vars_line[i], var, vals_line[i])

            if var in result and i < len(vals_line):
                result[var].append([val, val_line_num])
            elif var not in result and i < len(vals_line):
                result[var] = [[val, val_line_num]]

    def compare_sentences(self, section1: Section, section2: Section):
        """
        Description:
            Use a LineAnalyzer's compare_sentence(..) to compare sentences in a list.

        Args:
            section1 (Section): The Section with sentences to be compared against.
            section2 (Section): The Section with sentences to be processed.

        Returns:
            list[tuple]: Result diff deltas.
            list[int]: Line numbers in original golden config.
            list[int]: Line numbers in original user config.
            list[str]: Variables in golden lines.
            list[bool|str]: Info about whether any variable is an expression.
            list[str]: Values in user lines.
            list[int]: Value mismatch error counts in line pairs.
        """
        results = []
        content1 = section1.content
        content2 = section2.content

        missing_lines, extra_lines, adj_lines_1st, adj_lines_2nd = self.inspect_lines(section1, section2)

        # For paragraph2, further compare lines that share enough similarities.
        # First, set up 2 pointers to keep track of original line numbers in both paragraphs
        idx_in_ori_1st, idx_in_ori_2nd = 0, 0
        idx_in_ori_1st_list, idx_in_ori_2nd_list = [], []
        variables, is_expressions, values, value_mistach_errors = [], [], [], []
        var_val_dict = {}
        for i in range(len(adj_lines_1st)):
            vars_line, is_exprs_line, vals_line, errors_line = [], [], [], 0
            if adj_lines_2nd[i] == -1:
                results.append([(ERR_TYPE_MISSING_LINE, 0, len(content1[idx_in_ori_1st]), 0, 0),
                                (COL_LABEL_LINE_NUM_1, idx_in_ori_1st + section1.start_line, 0, 0, 0),])
                idx_in_ori_1st_list.append(idx_in_ori_1st + section1.start_line)
                idx_in_ori_2nd_list.append(-1)

                idx_in_ori_1st += 1
            elif adj_lines_2nd[i] != -1 and adj_lines_1st[i] == -1:
                results.append([(ERR_TYPE_EXTRA_LINE, 0, 0, 0, len(content2[idx_in_ori_2nd]))])
                idx_in_ori_1st_list.append(-1)
                idx_in_ori_2nd_list.append(idx_in_ori_2nd + section2.start_line)

                idx_in_ori_2nd += 1
            else:
                tuples, vars_line, is_exprs_line, vals_line, errors_line = self.line_analyzer.compare_sentence(
                    content1[idx_in_ori_1st], content2[idx_in_ori_2nd]
                )
                # Append a corresponding line num in paragraph 1 so that the front-end can use the info
                tuples.append((COL_LABEL_LINE_NUM_1, idx_in_ori_1st + section1.start_line, 0, 0, 0))
                results.append(tuples)
                self._collect_line_var_val(
                    var_val_dict, vars_line, is_exprs_line, vals_line, idx_in_ori_2nd + section2.start_line
                )
                idx_in_ori_1st_list.append(idx_in_ori_1st + section1.start_line)
                idx_in_ori_2nd_list.append(idx_in_ori_2nd + section2.start_line)

                idx_in_ori_1st += 1
                idx_in_ori_2nd += 1

            # Collect variables and values per line no matter what
            variables.append(vars_line)
            is_expressions.append(is_exprs_line)
            values.append(vals_line)
            value_mistach_errors.append(errors_line)

        # Annotate missing/extra lines, make new content, and replace the old one
        new_content_len = len(adj_lines_2nd)
        new_content = [None] * new_content_len
        # Initialize new content start pointer and pointer for line in original paragraph 2
        start_idx, ptr_2nd = 0, 0

        for i in range(start_idx, new_content_len):
            if results[i][0][0] == ERR_TYPE_MISSING_LINE:
                new_content[i] = "(missing line from golden)"
            else:
                new_content[i] = content2[ptr_2nd].replace("\n", "")
                ptr_2nd += 1

        section2.content.clear()
        section2.content = new_content

        return (
            results,
            idx_in_ori_1st_list, idx_in_ori_2nd_list,
            variables, is_expressions, values,
            value_mistach_errors, var_val_dict,
        )
