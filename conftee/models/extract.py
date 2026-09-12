import re
from difflib import SequenceMatcher

from ..utils.helpers import quick_is_device_title, quick_is_section_title

from .section import SECTION_TITLE_LINE_REGEX, SECTION_TITLE_REGEX, SECTION_TITLE_SUFFIX
from ..utils.constants import BLOCK_TYPE_DEVICE, BLOCK_TYPE_SECTION

# This is a more forgiving regex for device title that does not care if there are tildes at the end
# Note: has to allow "_" for integration tests
DEVICE_TITLE_LINE_REGEX = r"^\s*~+\s*([a-zA-Z0-9\-\_\#]+\s*)+\s*~*$"
DEVICE_TITLE_REGEX = r"[a-zA-Z\_\#][\-\w\s]+\s*"
COMMON_TERMS = [
    "router",
    "Router",
    "FW",
    "Firewall",
    "context",
    "hsrp",
    "HSRP",
    "vss",
    "VSS",
    "Standby",
    "Active",
    "building",
    "switch",
    "distribution",
    "access",
    "Test",
]
COMMON_TERM_LIKENESS_CUTOFF = 0.75


## Helper functions related to native struct extractor


def _like_common_term(word: str):
    """
    Description:
        Determine if a word has enough similarity with any words in the common words dictionary.
        This is mainly for preparation before seperating known device names like "fw25-ctx" from words like "FW Context".
    """
    most_sim_idx = 0
    max_similarity = 0.000
    for i in range(len(COMMON_TERMS)):
        comm_word = COMMON_TERMS[i]
        sm = SequenceMatcher(a=word, b=comm_word)
        if sm.ratio() > max_similarity:
            max_similarity = round(sm.ratio(), 3)
            most_sim_idx = i
    most_sim_word = COMMON_TERMS[most_sim_idx] if max_similarity > COMMON_TERM_LIKENESS_CUTOFF else ""

    return most_sim_word


def _extract_device_name(title_line: str) -> tuple[dict, list[str]]:
    # Remove line break at the end because it is not good for regex checking here
    title_line = title_line.replace("\n", "")
    if not bool(re.fullmatch(DEVICE_TITLE_LINE_REGEX, title_line)):
        return {}, []

    # Now that it is certain a section tile exists, search for device name (natrual words)
    matches = re.findall(DEVICE_TITLE_REGEX, title_line)
    # If not found, return empty string
    if not matches:
        return {}, []

    # A device title line's natural words are probably more than one. The first one is ususally device name if there
    #       is one, the rest words try to describe device role. So check if the first word is like a common term.
    #       If it is not, mark it as a device name. Else, assume no device name and treat everything as device role description.
    result = {}
    words_in_match = matches[0].rstrip().split()
    is_first_word_common = _like_common_term(words_in_match[0])
    if is_first_word_common:
        result["device"] = ""
        result["role"] = ("".join(matches)).rstrip()
    else:
        # If first word is not common, then assume it is a semi-unique device name
        result["device"] = words_in_match[0]
        result["role"] = (" ".join(words_in_match[1:])).rstrip()

    return result, "".join(matches[0:])


def _extract_section_name(title_line: str):
    matches = re.search(SECTION_TITLE_REGEX, title_line)
    if not matches:
        return ""
    else:
        # If the line is a title line then there should be only match, but just get the first match anyway
        #       this is why re.search was used instead of re.findall too.
        clip_len = len(matches[0]) - len(SECTION_TITLE_SUFFIX) - 1
        return matches[0][0:clip_len]


def _make_section_tuple(
    prev_section_cnt: int, prev_device_ptr: int, section_start_ptr: int, section_end_ptr: int, prev_section_title: str
):
    """
    Description:
        Make tuple for a section based on previous section count (prev_section_cnt).
        Note that all line numbers are incremented by 1, because overall assumption is line numbers start from 1.
    """
    result = None
    if prev_section_cnt == 1:
        # If previous section is the 1st one under current device, include lines between
        #       device title and that section title
        result = (
            prev_device_ptr + 1 + 1,
            section_start_ptr + section_end_ptr + 1,
            _extract_section_name(prev_section_title),
            BLOCK_TYPE_SECTION,
        )
    elif prev_section_cnt > 1:
        # If previous section is >= 2nd one under current device, only include lines between
        #       that section title and last non-title line (the line before current section)
        result = (
            section_start_ptr + 1,
            section_start_ptr + section_end_ptr + 1,
            _extract_section_name(prev_section_title),
            BLOCK_TYPE_SECTION,
        )

    return result



class Extract:

    @staticmethod
    def extract_struct(file_content: list[str]):
        """
        Description:
            Extract file structure from a config file written in the agreed format.

        Args:
            file_content (list[str]): Content read from a config file, each element storing one line

        Returns:
            list[tuple[int, int, str, str]]: A list of tuples that represents the structure of a config file

        Example:
            Input: ["~~~~ fw25-ctx FW context ~~~~",
                    "! #### USER PREFIX START ###",
                    "some commands",
                    "! #### USER PREFIX END #####",
                    "\n",
                    "~~~~ vss-a25-l25 ~~~",
                    "! #### VRF START ###########",
                    "some commands",
                    "! #### VRF END #############",
                    "\n",
                    "! #### USER PREFIX START ###",
                    "some commands",
                    "! #### USER PREFIX END #####"]
            Output: [(1, 1, 'fw25-ctx', 'd'), (2, 5, 'USER PREFIX', 's'),
                    (6, 6, 'vss-a25-l25', 'd'), (7, 10, 'VRF', 's'), (11, 13, 'USER PREFIX', 's')]
        """
        result = []
        prev_device_ptr, prev_section_cnt = 0, 0
        curr_line_ptr, section_start_ptr, section_end_ptr = 0, 0, 0
        for line in file_content:
            line_strip = line.lstrip()
            if quick_is_device_title(line=line_strip):
                # This means this line is a potential device title line
                if bool(re.match(DEVICE_TITLE_LINE_REGEX, line)):
                    # If it indeed is, store tuple for the previous section, if there is one.
                    # Call _make_section_tuple(.) to make tuple with 1-indexed line numbers.
                    tmp_tuple = _make_section_tuple(
                        prev_section_cnt,
                        prev_device_ptr,
                        section_start_ptr,
                        section_end_ptr,
                        file_content[section_start_ptr],
                    )
                    result.append(tmp_tuple) if tmp_tuple else 0 == 0

                    # Then store tuple for this device block, which is only one line.
                    # still 1-indexed line numbers.
                    device_info, words = _extract_device_name(line)
                    device_name, device_role = device_info["device"], device_info["role"]
                    # TODO: Maybe can move this "beautifing" of device name into another function
                    #       to handle more situations and be more scalable
                    if device_name:
                        if ("distribution " in words) or ("access " in words):
                            tuple_name = device_name + " " + device_role
                        else:
                            tuple_name = device_name
                    else:
                        tuple_name = device_role

                    result.append((curr_line_ptr + 1, curr_line_ptr + 1, tuple_name, BLOCK_TYPE_DEVICE))

                    # Then reset section line pointers and start recording this device's sections
                    section_start_ptr, section_end_ptr = curr_line_ptr, 0
                    prev_device_ptr, prev_section_cnt = curr_line_ptr, 0

            elif quick_is_section_title(line=line_strip):
                # This means this line is a potential section title line
                if bool(re.match(SECTION_TITLE_LINE_REGEX, line)):
                    # If it indeed is, store tuple for the previous section, if there is one.
                    # Call _make_section_tuple(.) to make tuple with 1-indexed line numbers.
                    tmp_tuple = _make_section_tuple(
                        prev_section_cnt,
                        prev_device_ptr,
                        section_start_ptr,
                        section_end_ptr,
                        file_content[section_start_ptr],
                    )
                    result.append(tmp_tuple) if tmp_tuple else 0 == 0

                    # Then reset section line pointers and start recording current section
                    section_start_ptr, section_end_ptr = curr_line_ptr, 0
                    prev_section_cnt += 1
                else:
                    # If it is not (such as section end line), increment section end pointer
                    section_end_ptr += 1

            else:
                # If it is not a potential title line, count it inside the current section, so also increment section end pointer
                section_end_ptr += 1

            curr_line_ptr += 1

        # Finally append the tuple for last section under last device
        tmp_tuple = _make_section_tuple(
            prev_section_cnt, prev_device_ptr, section_start_ptr, section_end_ptr, file_content[section_start_ptr]
        )
        result.append(tmp_tuple) if tmp_tuple else 0 == 0

        return result

    @staticmethod
    def _extract_structs(golden_content, user_content):
        """
        Description:
            Extract the block structures of both config files.

        Returns:
            tuple: (golden file structure, user file structure)
        """
        file_struct_1 = Extract.extract_struct(golden_content)
        file_struct_2 = Extract.extract_struct(user_content)

        return file_struct_1, file_struct_2
