import re

# A strict regex that demands a format like this "! ##### title name ###"
#SECTION_TITLE_LINE_REGEX = r'^!\s*#+\s([A-Z]+\s*)START\s#+\s*$'
# A chill regex that only requires ! and some "#" before the title name and doesn't care very much after
SECTION_TITLE_LINE_REGEX = r'^\s*!\s*#+\s([A-Z]+\s*)+START\s[0-9a-zA-Z#\s]*$'
SECTION_TITLE_REGEX = r'([A-Z]+\s*)+START'
SECTION_TITLE_SUFFIX = "START"

class Section:

    def __init__(self, content:list[str], start_line:int, end_line:int, is_golden:bool=False):
        """
        Description:
            Instantialize. This class represents a section in a config file.
            
        Args:
            content (list[str]): The content of this section.
            start_line (int): The line number where this section starts, i.e. the line number of its block header. Preferrably 1-indexed when starting from the start of a text file.
            is_golden (bool, optional): Whether this section is from a golden config. Defaults to False.
        """
        self.content = content
        self._adjust_first_line(self.content)
        self.start_line = start_line
        self.is_golden = is_golden
        # Calculated start and end line numbers tuple
        self.line_numbers = (start_line, end_line)

    def _adjust_first_line(self, content:list[str]):
        # Probably due to it recursive nature, if there is only one "\n" in the first line of the first sequence,
        # the Differ instance might match it with another "\n" in the second sequence, usually much later (large line number)
        # So protect it against that by adjusting the "\n" if there is one
        if content[0] == "\n":
            content[0] = " \n"

    def is_empty(self):
        return len(self.content) <= 0