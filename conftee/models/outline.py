from .section import Section
from .extract import _extract_device_name
from ..utils.constants import BLOCK_TYPE_DEVICE, BLOCK_TYPE_SECTION


class Outline:

    def __init__(self, file_content: list[str], file_struct: list[tuple], is_golden: bool = False):
        """
        Description:
            Instantiate. This class stores contents of configs and slices them into device/section blocks.

        Args:
            file_content (list[str]): Content of a config as list of strings.
            file_struct (list[tuple]): Structure of the config represented by tuples of designated format.
            is_golden (bool, optional): Whether this config is golden config. Defaults to False.
        """
        self.is_golden = is_golden
        # Reserve a copy of original content, so that after augmenting some lines while diff checking,
        #        this can be used as a source of truth for post-processings.
        self.file_content = file_content
        self.file_struct = file_struct

        # Devices can be identified by just the device block title lines, so no need for objects.
        self.device_titles: list[str] = []
        # List for sections.
        self.sections: list[Section] = []

        # Slice content into device/section blocks annotations along the way
        self._init_blocks(file_content, file_struct, self.sections, self.device_titles)

    def _init_blocks(
        self, file_content: list[str], file_struct: list[tuple], res_sections: list[Section], res_devices: list[str]
    ):
        """
        Description:
            Initialize device/section blocks. Expects to take in the class properties self.sections etc and fill the lists in-place.
        """
        if len(file_content) <= 0 or len(file_struct) <= 0:
            return

        # If both file_content and file_struct are non-empty, start slicing.
        res_sections.clear()
        res_devices.clear()

        for block in file_struct:
            start_line, end_line = block[0], block[1]

            if end_line < start_line or start_line < 0 or end_line < 0:
                raise ValueError(
                    f'Incomprehensible block starting from "{start_line}" to "{end_line}" at file struct tuple {block}. Expecting indices to be >=0 and end >= start.'
                )

            if block[3] == BLOCK_TYPE_SECTION:
                section = Section(
                    content=file_content[start_line - 1 : end_line],
                    start_line=start_line,
                    end_line=end_line,
                    is_golden=self.is_golden,
                )
                res_sections.append(section)
            elif block[3] == BLOCK_TYPE_DEVICE:
                title_line = file_content[start_line - 1]
                device_string_dict, device_name = _extract_device_name(title_line)
                res_devices.append(device_name.rstrip()) if device_name else res_devices.append(device_string_dict['role'])
            else:
                raise ValueError(
                    f'Incomprehensible block type "{block[3]}" at file struct tuple {block}. Expecting "d" or "s".'
                )
