import re
from typing import Union
from difflib import SequenceMatcher

from .section import SECTION_TITLE_LINE_REGEX
from ..utils import schema as schema_module
from ..utils.constants import GENERAL_IPV4_REGEX

VARIABLE_REGEX = r"\{[\-\#\w]+\}"
EXPRESSION_REGEX = r"\{\{[\-\#\w]+\}[-+][0-9]\}"
INFRQ_CHAR_FOR_VARIABLE, INFRQ_CHAR_FOR_IPV4 = ";", ":"


class LineAnalyzer:

    def __init__(self, schema=None):
        """
        Description:
            Instantiate. This class handles comparison at a signle (pair of) line level.

        Args:
            schema (Schema, optional): The vocabulary to validate values against.
                Defaults to the bundled cisco-campus schema while the engine is
                being migrated off module-level constants; see utils/schema.default.
        """
        self.schema = schema if schema is not None else schema_module.default()
        self.ipv4_variables = self.schema.variables_with_arithmetic("ipv4")

    def variable_is_value_match(self, variable: str, value: str) -> bool:
        """
        Description:
            Check if a value 100% matches a variable's format.

        Args:
            variable (str): The variable (name of regex) to be compared against.
            value (str): The value to be processed.

        Returns:
            bool: Whether the value is a full match.

        Examples:
            variable_is_value_match("Vlan_ID_user", "123") will return: True
            variable_is_value_match("Vlan_ID_user", "a123") will return: False
        """
        try:
            regex = self.schema.regex_for(variable)
        except ValueError:
            print(f"Key {variable} lookup in the regex dictionary failed.")
            return False

        try:
            is_match = bool(regex.fullmatch(value))
        except Exception as e:
            raise RuntimeError(f"Regex match error {e.msg}")

        return is_match

    def word_pair_up_brackets(self, word: str):
        """
        Description:
            Try to find bracket pairs in a substring.

        Returns:
            int: Number of excessive brackets. 0 means all brackets are paired or no brackets.
        """
        stack, stack_idx = [], []
        pairs_idx = []
        for i in range(len(word)):
            if word[i] == "{":
                stack.append("{")
                stack_idx.append(i)
            elif word[i] == "}":
                if stack and stack[-1] == "{":
                    pairs_idx.append((stack_idx.pop(), i))
                    stack.pop()
                else:
                    stack.append("}")

        exessive_brackets = len(stack)

        return exessive_brackets

    def word_find_variables(self, word: str):
        """
        Description:
            Search for variables and expressions, by regex matching.
        """
        var_matches_iter = re.finditer(VARIABLE_REGEX, word)
        expr_matches_iter = re.finditer(EXPRESSION_REGEX, word)

        variables, variables_idx, expressions, expressions_idx = [], [], [], []

        for m in var_matches_iter:
            variables.append(m.group(0))
            variables_idx.append((m.start(), m.end() - 1))

        for m in expr_matches_iter:
            expressions.append(m.group(0))
            expressions_idx.append((m.start(), m.end() - 1))

        return variables, variables_idx, expressions, expressions_idx

    def word_extract_variables(self, word: str, adjust_idx: int = 0):
        """
        Description:
            Find variables with paired curly brackets in a substring. Typically a word in a line. 

        Args:
            word (str): The substring to be processed.
            adjust_idx (int, optional): Extra starting index of the string if it was a word splitted from a line. Defaults to 0.

        Returns:
            list[str]: Extracted variables.
            list[tuple]: Adjusted indices of curly brackets in the string.
            list[bool|str]: Whether extracted variables are part of an expression or not.
            str: Error message indicating abnormal brackets pairing, or an empty string if no error.

        Examples:
            input ("jsdh{test}") will have:
                ['{test}'], [(4, 9)], [False],
                None as error message.
            input ("jsdh{test}}") will have:
                ['{test}'], [(4, 9)], [False],
                "Error: There are 1 excessive brackets" as error message.
            input ("{var1}{{var2}-1}") will have:
                ['{var1}', '{{var2}-2}'], [(0, 5), (7, 16)], [False, '{var2}']
                None as error message.
        """
        # Search for all variables and expressions
        variables, variables_idx, expressions, expressions_idx = self.word_find_variables(word)

        # Then start to merge the indices and collect the outmost brackets
        ptr_in_vars_idx, ptr_in_exprs_idx = 0, 0
        variables_merged, outmost_bracket_pairs, is_expression = [], [], []
        # If there is an expression, then it must have a variable, so number of variables
        # always >= number of expressions. So loop based on number of variables.
        if len(expressions_idx) > 0:
            for tuple in variables_idx:
                if tuple[0] >= expressions_idx[ptr_in_exprs_idx][0]:
                    # This means this pair is inside an expression, record the expression instead
                    variables_merged.append(expressions[ptr_in_exprs_idx])
                    outmost_bracket_pairs.append(expressions_idx[ptr_in_exprs_idx])
                    is_expression.append(variables[ptr_in_vars_idx])

                    ptr_in_exprs_idx += 1
                else:
                    # This means this pair is not inside an expression, simply record this pair
                    variables_merged.append(variables[ptr_in_vars_idx])
                    outmost_bracket_pairs.append(tuple)
                    is_expression.append(False)

                ptr_in_vars_idx += 1

            outmost_bracket_pairs.extend(variables_idx[ptr_in_vars_idx:])

        else:
            variables_merged = variables
            outmost_bracket_pairs.extend(variables_idx)
            is_expression.extend([False] * len(variables))

        # Adjust the indices by adding the starting index of this word to them
        for i in range(len(outmost_bracket_pairs)):
            outmost_bracket_pairs[i] = (adjust_idx + outmost_bracket_pairs[i][0],
                                        adjust_idx + outmost_bracket_pairs[i][1])

        # Finally check if there are un-paired brackets and record the error, if variables exist
        error_msg = None
        if variables:
            excess_br = self.word_pair_up_brackets(word)
            if excess_br > 0:
                error_msg = f"Error: There are {self.word_pair_up_brackets(word)} excessive brackets"

        return variables_merged, outmost_bracket_pairs, is_expression, error_msg

    def word_extract_ipv4s(self, word: str, adjust_idx: int = 0):
        """
        Description:
            Extract possible IPv4 addresses using regex.
        """
        matches = re.finditer(GENERAL_IPV4_REGEX, word)

        ips, indices = [], []
        for match in matches:
            ip = match.group()
            if all(0 <= int(octet) <= 255 for octet in ip.split(".")):
                # Only collect if all octets are in [0,255], because the regex pattern does not check this
                ips.append(ip)
                indices.append((match.start() + adjust_idx, match.end() + adjust_idx))
        
        if ips:
            return indices
        else:
            return None

    def word_slice_at_brackets(self, word_start:int, word_end:int, bracket_pairs:list[tuple]):
        merged:list[tuple[int, int]] = []
        has_pre, has_suf = False, False
        left_overs, start, end = [], word_start, bracket_pairs[0][0]

        # Store "prefix" leftover
        if end > start:
            left_overs.append((start, end))
            merged.append((start, end))
            has_pre = True

        # Store variable slices and in-between leftovers
        for j in range(len(bracket_pairs) - 1):
            # This is a variable slice
            merged.append((bracket_pairs[j][0], bracket_pairs[j][1] + 1))
            start = bracket_pairs[j][1]
            end = bracket_pairs[j + 1][0]

            if end > start:
                # This means there is an in-between leftover
                left_overs.append((start + 1, end))
                merged.append((start + 1, end))

        # Store the last variabe in to merged list
        merged.append((bracket_pairs[len(bracket_pairs)-1][0], bracket_pairs[len(bracket_pairs)-1][1] + 1))

        # Store "suffix" leftover
        if word_end >= (bracket_pairs[len(bracket_pairs)-1][1] + 2):
            left_overs.append((bracket_pairs[len(bracket_pairs)-1][1] + 1, word_end))
            merged.append((bracket_pairs[len(bracket_pairs)-1][1] + 1, word_end))
            has_suf = True

        return left_overs, merged, has_pre, has_suf

    def is_title_line(self, sentence: str):
        """
        Description:
            Check if a sentence is a section title line using regex match.
        """
        return bool(re.fullmatch(SECTION_TITLE_LINE_REGEX, sentence))

    def tidy_sentence_preserve_indent(self, sentence: str):
        """
        Description:
            Remove exessive spaces between words, remove trailing spaces and preserve leading spaces.
            Not sure if this would be useful, so keeping it temporarily.

        Args:
            sentence (str): The sentence to be processed.

        Returns:
            str: Result string.
            int: The end index of leading spaces.

        Examples:
            Before:<leading spaces___>     A {sentence} with leading, trailing spaces and extra <____>   spaces before processed.  <___trailing spaces>
            After:<leading spaces___>     A {sentence} with leading, trailing spaces and extra spaces before processed.
        """
        beggining_len: int = len(sentence) - len(sentence.lstrip())
        words = sentence.split()
        leading_str = sentence[0:beggining_len]
        reorganized = leading_str + " ".join(words)
        return reorganized, beggining_len

    def split_sentence(self, sentence: str, delimeter: str) -> tuple[list[str], list[int]]:
        """
        Description:
            Split a sentence by a delimeter and store indices of resulting words.

        Args:
            sentence (str): The sentence to be processed.
            delimeter (str): A delimeter to mark the splitting points.

        Returns:
            list[str]: The resulting words.
            list[int]: Start indices for each words in the original string.

        Examples:
            split_sentence("has a {var1} here.", " ") returns
                ['has ', 'a ', '{var1} ', 'here.']  [0, 4, 6, 13]
        """
        words, indices = [], []

        start_index = 0  # Starting index for the first word
        for index, char in enumerate(sentence):
            # Check if the current character is a space or a punctuation mark (e.g., comma)
            if char == delimeter or index == len(sentence) - 1:
                words.append(sentence[start_index : index + 1].strip(" \n"))
                indices.append(start_index)
                start_index = index + 1

        return words, indices

    def gather_variables(self, sentence_g:str):
        words_g, indices_g = self.split_sentence(sentence_g, " ")
        variables_idx, has_ipv4_g = [], False
        for i in range(len(words_g)):
            var_list, bracket_pairs, is_expression, err_msg = self.word_extract_variables(words_g[i], indices_g[i])
            if len(var_list) > 0:
                # If has variables, append them to the list, and take note of whether there are IPv4 variables
                variables_idx.extend(bracket_pairs)
                for var in var_list:
                    if var[1 : len(var) - 1] in self.ipv4_variables:
                        has_ipv4_g = True

        return variables_idx, has_ipv4_g

    def mask_variables(self, sentence: str, var_idx_list: list[tuple[int, int]]):
        """
        Description:
            "Mask" variables in a sentence with natrually infrequent characters to protect them.

        Args:
            sentence (str): The sentence to be processed.
            var_idx_list (list[tuple[int, int]]): A list of indices of detected variables in the sentence.

        Returns:
            str: A new sentence with "masked" variables.

        Examples:
            mask_variables("has a {var1} and {vari2} here.", [(6, 12), (17, 24)]) returns
                           "has a {,,,,} and {,,,,,} here."
        """
        new_sentence = ""
        infreq_char = INFRQ_CHAR_FOR_VARIABLE

        if len(var_idx_list) > 0:
            new_sentence = sentence[0 : var_idx_list[0][0]]

            for i in range(len(var_idx_list) - 1):
                var_len = var_idx_list[i][1] - var_idx_list[i][0] - 1
                new_sentence += "{" + infreq_char * var_len + "}"
                new_sentence += sentence[(var_idx_list[i][1] + 1) : var_idx_list[i + 1][0]]

            if len(var_idx_list) > 1:
                last_idx = len(var_idx_list) - 1
            else:
                last_idx = 0

            var_len = var_idx_list[last_idx][1] - var_idx_list[last_idx][0] - 1
            new_sentence += "{" + infreq_char * var_len + "}"
            new_sentence += sentence[(var_idx_list[last_idx][1] + 1) :]
        else:
            new_sentence = sentence[:]

        return new_sentence

    def gather_ipv4_values(self, sentence_u:str):
        words_u, indices_u = self.split_sentence(sentence_u, " ")

        values_ipv4_idx = []
        for i in range(len(words_u)):
            value_ipv4_idx = self.word_extract_ipv4s(words_u[i], indices_u[i])
            if value_ipv4_idx:
                values_ipv4_idx.extend(value_ipv4_idx)

        return values_ipv4_idx

    def mask_values_ipv4(self, sentence: str, val_idx_list: list[tuple[int, int]]):
        """
        Description:
            "Mask" IPv4 address values in a sentence with natrually infrequent characters to protect them.
            Note: This looks similar to mask_variables(.), but variables have extra curly brackets, and this function
            might need to be scaled in the future, so keeping them seperate for now.

        Args:
            sentence (str): The sentence to be processed.
            val_idx_list (list[tuple[int, int]]): A list of indices of detected values in the sentence.

        Returns:
            str: A new sentence with "masked" variables.

        Examples:
            mask_variables("has a 142.103.113.232 and 255.255.255.240 values.", [(6, 21), (26, 41)]) returns
                           "has a ::::::::::::::: and ::::::::::::::: values."
        """
        new_sentence = ""
        infreq_char = INFRQ_CHAR_FOR_IPV4

        if len(val_idx_list) > 0:
            new_sentence = sentence[0 : val_idx_list[0][0]]

            for i in range(len(val_idx_list) - 1):
                val_len = val_idx_list[i][1] - val_idx_list[i][0]
                new_sentence += infreq_char * val_len
                new_sentence += sentence[(val_idx_list[i][1]) : val_idx_list[i + 1][0]]

            if len(val_idx_list) > 1:
                last_idx = len(val_idx_list) - 1
            else:
                last_idx = 0

            val_len = val_idx_list[last_idx][1] - val_idx_list[last_idx][0]
            new_sentence += infreq_char * val_len
            new_sentence += sentence[(val_idx_list[last_idx][1]) :]
        else:
            new_sentence = sentence[:]

        return new_sentence

    def gather_values_until_depletion(
        self, variables_g: list[str], curly_bracket_pairs: list[tuple], words_u: list[str], words_u_idx: list[int]
    ):
        """
        Description:
            Take an existing variables_g from golden and corresponding substring from user sentence, and try to
            pair words with variables until either of them is depleted, and return words and their indices.

        Note:
            It is possible that the number of words is different than the number of variables. This function's main purpose is to consider that.

        Example:
            variables_g is ['{FW_context_name}','{VRF_name}','{int_#}'] from 1st substring "{FW_context_name}-VRFGLUE={VRF_name} {int_#}"
            words_u is ['pre', 'NOVA33'] from 2nd substring "pre NOVA33"
            Output'd be ['pre', 'NOVA33'], [0, 4]
        """
        # Currently this function pick up values based on the length of both lists, and
        # whether there are consequtive variables

        values, values_idx = [], []
        i, j = 0, 0
        while j <= len(variables_g) - 1:
            if i > len(words_u) - 1:
                break
            else:
                # Try to search substrings in words_u[i] that match current variables_g[j]
                # This is to handle the case of 2 consequtive variables in one word
                conseq_vars_num = 0
                if j + 1 <= len(variables_g) - 1:
                    if curly_bracket_pairs[j + 1][0] == curly_bracket_pairs[j][1] + 1:
                        # This means there is a consecutive variable after current one
                        conseq_vars_num = 2

                if conseq_vars_num >= 2:
                    # If have consecutive variables, try to find one for each
                    cnt_matched = 0
                    for k in range(conseq_vars_num):
                        curr_var = variables_g[j + k][1:-1]
                        curr_match = self.schema.regex_for(curr_var).search(words_u[i])
                        if curr_match:
                            cnt_matched += 1
                            curr_matched_word = words_u[i][curr_match.start() : curr_match.end()]
                            values.append(curr_matched_word)
                            values_idx.append(words_u_idx[i] + curr_match.start())

                    if cnt_matched == 0:
                        # After trying, if none matches, still need to append word in word_u
                        values.append(words_u[i])
                        values_idx.append(words_u_idx[i])

                    j += conseq_vars_num

                else:
                    # If not, just append the whole word
                    values.append(words_u[i])
                    values_idx.append(words_u_idx[i])
                    j += 1

            i += 1

        return values, values_idx

    def mark_values_and_errors(self, new_opcodes, value_mismatch_error,
                               variables_g:list[str], bracket_pairs:list[tuple],
                               is_expression_g:list[Union[bool, str]], left_overs:list[tuple[int, int]],
                               words_u:list[str], words_u_idx:list[int],
                               str_u_start:int):
        """
        Description:
            Take an existing variables_g that have some corresponding values, gather all possible values into higher level data,
            mo matter whether they are mismatching or not.
            Modifies new_opcodes and value_mismatch_error in-place.
        """
        local_new_opcodes, local_mismatches = [], 0

        j, left_over_idx = 0, 0
        for i in range(len(variables_g)):
            if j > len(words_u) - 1:
                break
            else:
                # If variable is an expression then check the variable inside it, otherwise there will be a KeyError
                var = variables_g[i] if is_expression_g[i] is False else is_expression_g[i]
                if self.variable_is_value_match(var[1 : (len(var) - 1)], words_u[j]):
                    new_op_0 = "replace-var"
                else:
                    new_op_0 = "replace-var-err"
                    local_mismatches += 1

                # Actually if any value is missing, it can only be 2 variables versus 1 value
                # so we can directly use opcode[3] and opcode[4], but using info of words_u just to stay consistent
                new_opcode = (
                    new_op_0,
                    bracket_pairs[j][0],
                    bracket_pairs[j][1] + 1,
                    str_u_start + words_u_idx[j],
                    str_u_start + words_u_idx[j] + len(words_u[j]),
                )
                local_new_opcodes.append(new_opcode)

                # Afterwards, have to take care of any leftover between this variable and the next one
                # The passed in left_overs indices list should be seamless with the variable indices
                if len(left_overs) > 0 and left_over_idx < len(left_overs):
                    if left_overs[left_over_idx][0] == bracket_pairs[j][1] + 1:
                        # This means this leftover is following the current variable
                        new_opcode = (
                            "replace",
                            left_overs[left_over_idx][0],
                            left_overs[left_over_idx][1],
                            str_u_start + words_u_idx[j] + len(words_u[j]),
                            str_u_start + words_u_idx[j] + len(words_u[j]),
                        )
                        local_new_opcodes.append(new_opcode)

                        left_over_idx += 1

            j += 1

        new_opcodes.extend(local_new_opcodes)
        value_mismatch_error[0] += local_mismatches

    def mark_missing_values(self, new_opcodes, value_mismatch_error,
                            counter_range:tuple[int, int],
                            bracket_pairs:list[tuple],
                            pos_in_u:int):
        """
        Description:
            Take an existing variables_g that definately do not have corresponding values, and report them into higher level data.
            Modifies new_opcodes and value_mismatch_error in-place.
        """
        for j in range(counter_range[0], counter_range[1]):
            value_mismatch_error[0] += 1

            # Currently not checking exact value-variable correspondence, so if there are missing values
            # the value-less variables would be at the end of the list, thus for sure at opcode[4].
            # This might change in the future though.
            new_opcode = (
                "replace-var-err",
                bracket_pairs[j][0],
                bracket_pairs[j][1] + 1,
                pos_in_u,
                pos_in_u,
            )
            new_opcodes.append(new_opcode)

    def add_prefix_opcode(self, new_opcodes, op: str, prefix_slice: tuple[int, int], pos_in_u: int):
        new_opcodes.append(
            (op, prefix_slice[0], prefix_slice[1], pos_in_u, pos_in_u + prefix_slice[1] - prefix_slice[0])
        )

    def add_suffix_opcode(self, new_opcodes, op: str, suffix_slice: tuple[int, int], pos_in_u: int):
        new_opcodes.append(
            (
                op,
                suffix_slice[0],
                suffix_slice[1],
                pos_in_u,
                pos_in_u,
            )
        )

    def compare_sentence(self, sentence1: str, sentence2: str):
        """
        Description:
            Use difflib.SequenceMatcher to calculate diff deltas of one sentence compared to another sentence.
            And augment the opcodes with extra info involving variables (all caps names in curly brackets).

        Args:
            sentence1 (str): The sentence to be compared against. Ideally from a golden config file.
            sentence2 (str): The sentence to be processed.

        Returns:
            list[tuple]: A list of operations telling how to change sentence2 into sentence1. Tuple format is the same as the vanilla SequenceMatcher's.

        Examples:
            sentence1 = "no route {VRF_name} {User_prefix} {User_prefix_netmask} {GW-VRFGLUE_IP} 2"
            sentence2 = "no route namexx 142.103.113.232 255.255.255.240"
            Output'd be: [('equal', 0, 9, 0, 9), ('replace-var-err', 9, 19, 9, 15), ('equal', 19, 20, 15, 16), ('replace-var', 20, 33, 16, 31), ('equal', 33, 34, 31, 32), ('replace-var', 34, 55, 32, 47), ('equal', 55, 56, 47, 48), ('replace-var-err', 56, 71, 48, 48), ('delete', 71, 73, 48, 48)]
                        ['VRF_name', 'User_prefix', 'User_prefix_netmask', 'GW-VRFGLUE_IP']
                        ['namexx', '142.103.113.232', '255.255.255.240', '']
                        2
        """
        ## Clean up excessive while spaces between words for SequenceMacther to work better
        sentence1 = self.tidy_sentence_preserve_indent(sentence1)[0]
        sentence2 = self.tidy_sentence_preserve_indent(sentence2)[0]

        # Split 1st sentence and get variable indices
        variables_idx, has_ipv4_g = self.gather_variables(sentence_g=sentence1)

        # "Mask" the variables with natrually infrequent characters to protect them.
        #    Because when variable name share any substrings with the supposed value in sentence2, SequenceMatcher would split the variable, which we don't want.
        #    E.g, when there are "{first}" and "second", SequenceMatcher would split "{fir", "s" and "t}".
        new_sentence1 = self.mask_variables(sentence1, variables_idx)

        if has_ipv4_g:
            # If golden line has IPv4 variables, inspect if user line also has IPv4 values
            # If there are, "Mask" them too
            values_ipv4_idx = self.gather_ipv4_values(sentence2)
            new_sentence2 = self.mask_values_ipv4(sentence2, values_ipv4_idx)
            sm = SequenceMatcher(None, new_sentence1, new_sentence2)
        else:
            sm = SequenceMatcher(None, new_sentence1, sentence2)

        ## Preprocessing done. Start to annotate vanilla opcodes.
        opcodes = sm.get_opcodes()
        variables, values, new_opcodes, is_expressions, value_mismatch_error = [], [], [], [], [0]
        for i in range(len(opcodes)):
            # Get variables and brackets for this golden substring
            opcode = opcodes[i]
            str_g = sentence1[opcode[1] : opcode[2]]
            variables_g, curly_bracket_pairs, is_expression_g, err_msg = self.word_extract_variables(str_g, opcode[1])

            has_pre, has_suf = False, False
            if variables_g:
                left_overs, slices, has_pre, has_suf = self.word_slice_at_brackets(opcode[1], opcode[2], curly_bracket_pairs)

            if opcode[0] == "replace" and variables_g:
                # If has a counterpart and has >= 1 variables, inspect the counterpart and try to find values.
                # Store 2nd substring in a temp string.
                str_u = sentence2[opcode[3] : opcode[4]].rstrip("\n")

                if has_pre:
                    self.add_prefix_opcode(new_opcodes, "replace", prefix_slice=slices[0], pos_in_u=opcode[3])

                # Since a 'replace' op might mark a substring with more than one word, split the subtring try to pair them up.
                words_u, words_u_idx = self.split_sentence(str_u, " ")
                tetative_values, tetative_values_idx = self.gather_values_until_depletion(
                    variables_g=variables_g, curly_bracket_pairs=curly_bracket_pairs,
                    words_u=words_u, words_u_idx=words_u_idx,
                )

                # Then handle the middle part.
                mid_leftovers = []
                if has_pre and has_suf:
                    mid_leftovers.extend(left_overs[1:-1])
                elif has_pre and not has_suf:
                    mid_leftovers.extend(left_overs[1:])
                elif not has_pre and has_suf:
                    mid_leftovers.extend(left_overs[:-1])
                else:
                    mid_leftovers.extend(left_overs)
                # Call helper function to compare variables/values and mark leftover substrings
                self.mark_values_and_errors(
                    new_opcodes, value_mismatch_error,
                    variables_g=variables_g, bracket_pairs=curly_bracket_pairs, is_expression_g=is_expression_g, left_overs=mid_leftovers,
                    words_u=tetative_values, words_u_idx=tetative_values_idx,
                    str_u_start=opcode[3],
                )

                if len(tetative_values) < len(variables_g):
                    # This means there are missing values in this substring; probably just one, but still loop it
                    self.mark_missing_values(new_opcodes, value_mismatch_error,
                                             counter_range=(len(variables_g) - len(tetative_values), len(variables_g)),
                                             bracket_pairs=curly_bracket_pairs,
                                             pos_in_u=opcode[4])

                    # Then append the values list with void values to mark them
                    num_of_missing_vals = len(variables_g) - len(tetative_values)
                    tetative_values.extend([""] * num_of_missing_vals)

                if has_suf:
                    self.add_suffix_opcode(
                        new_opcodes, "replace", suffix_slice=slices[len(slices) - 1], pos_in_u=opcode[4]
                    )

                # Collect varaibles and values in the end
                # Remove curly brackets around variable names
                for j in range(len(variables_g)):
                    variables_g[j] = variables_g[j][1 : (len(variables_g[j]) - 1)]
                # Append them
                variables.extend(variables_g)
                values.extend(tetative_values)
                is_expressions.extend(is_expression_g)

            elif opcode[0] == "delete" and variables_g:
                # If lacks a counterpart and has >= 1 full variables, certainly some values are missing; just mark those
                if has_pre:
                    self.add_prefix_opcode(new_opcodes, "delete", prefix_slice=slices[0], pos_in_u=opcode[3])

                self.mark_missing_values(new_opcodes, value_mismatch_error,
                                         counter_range=(0, len(variables_g)),
                                         bracket_pairs=curly_bracket_pairs,
                                         pos_in_u=opcode[3])

                if has_suf:
                    self.add_suffix_opcode(
                        new_opcodes, "delete", suffix_slice=slices[len(slices) - 1], pos_in_u=opcode[4]
                    )

                # Collect varaibles and values in the end
                # Remove curly brackets around variable names
                for j in range(len(variables_g)):
                    variables_g[j] = variables_g[j][1 : (len(variables_g[j]) - 1)]
                # Append them
                variables.extend(variables_g)
                values.extend([""] * len(variables_g))
                is_expressions.extend(is_expression_g)

            else:
                # Don't need to annotate the opcode for 'equal' or 'insert', just copy
                new_opcodes.append(opcode)

        return new_opcodes, variables, is_expressions, values, value_mismatch_error[0]
