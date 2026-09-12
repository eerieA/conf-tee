import os, json


def get_files_in_dir(directory:str):
    """
    Description:
        An internal UI helper function to get files under a directory.
    """
    with os.scandir(directory) as entries:
        return [entry.name for entry in entries if entry.is_file()]
        
class ReadConfig:
    """
    Description:
        *Util* A class hosting methods for parsing input data from various sources.
    """

    # UI helper functions

    @staticmethod
    def is_file_in_dir(file_name:str, directory:str):
        files = get_files_in_dir(directory)
        return file_name in files
        
    @staticmethod
    def prompt_select_file(directory:str, prompt:str):
        files = get_files_in_dir(directory)
        print("\n".join(files))
        input_file_name = input(prompt)
        if not ReadConfig.is_file_in_dir(input_file_name, directory):
            input_file_name = ""
        return input_file_name

    # Parsers from here

    @staticmethod
    def read_config_from_txt(txt_full_path: str, limit: int = 1000) -> list[str]:
        """
        Description:
            *Static* Read config from a binary file which should be in plain text format.

        Args:
            txt_full_path (str): Full path of the file. For example "./folder/test.txt".
            limit (int): A limit to the max number of lines to be read. Defaults to 1000.
            According to client, a config file usually has under 100 lines. So Please adjust this limit if that changes.

        Returns:
            list[str]: Content read from the file as a list.
        """
        file_content = []
        safe_counter = 0
        try:
            with open(txt_full_path, "r") as file:
                # Using a while and readline() instead of readlines() because there might be a need to retain the empty line
                #       before EOF. And readlines() ignores that if there is one.
                # Also, use a counter to prevent stucking on file that is somehow too long.
                while safe_counter <= limit:
                    line = file.readline()
                    if not line:
                        break
                    file_content.append(line)
                    safe_counter += 1
        except Exception as e:
            raise e

        # Normally readline() throws away a "\n" before EOF, so if there is one at the end of last line,
        #       it means there is an empty line before EOF. Therefore seperate that and append.
        last_line = file_content[len(file_content) - 1]
        if last_line[len(last_line) - 1] == "\n":
            file_content[len(file_content) - 1] = last_line[: len(last_line) - 1] + "\n"
            # Was intented to add a marker "\eof" but maybe not a good idea. Using "\n" instead.
            file_content.append("\n")
        else:
            # Was intented to add a marker "\eof" but maybe not a good idea. Using "\n" instead.
            file_content[len(file_content) - 1] += "\n"
        return file_content


    @staticmethod
    def read_config_from_json_str(user_config: str):
        """
        Description:
            *Static* Read config from a string which should at least in standard JSON format.
            Ideally has the format of a response GETed from the designated endpoint, but in one string (perhaps temp stored into a txt).

        Args:
            user_json (str): A string with standard JSON format.

        Returns:
            list[str]: Content converted from the JSON string as a list.
            list[str]: Devices (1st level keys) from the JSON string.
        """
        # Per official Python documentation, a protection is recommended.
        # This value is borrowed from https://www.ibm.com/docs/en/datapower-gateway/10.5.x?topic=20-json-parser-limits .
        max_byte_size = 4194304
        if len(user_config) > max_byte_size:
            raise ValueError(f"Input data exceeds the specified maximum byte size {max_byte_size}.")

        # This is an arbitrary length for padding '~'s in a device title line
        device_title_len = 86
        try:
            decoded = json.loads(user_config)
        except json.JSONDecodeError as e:
            raise ValueError(
                f'Input data "{user_config[0:min(10, len(user_config)-1)]}..." is not in JSON format. Parsing failed at {e.pos}.'
            )

        if not decoded:
            return [], []
        content = decoded["results"][0]
        devices = []
        for key in content.keys():
            # By this date a good response from the endpoint would have an 'id' key
            # in 1st level. Exclude it because it is not a device name.
            if key != "id":
                devices.append(key)
        all_lines = []
        for dvc in devices:
            lines_list = content[dvc]
            title_padding_len = round((device_title_len - len(dvc) - 2) / 2)
            all_lines.append("~" * title_padding_len + " " + dvc + " " + "~" * title_padding_len)
            all_lines.extend(lines_list)
        return all_lines, devices


    @staticmethod
    def read_config_from_response(user_config: dict[str, list[str]]):
        """
        Description:
            *Static* Read config from response from the API endpoint. Tweak this if API response format changes.

        Args:
            user_config (dict[str, list[str]]): A dict of devices and their configs.

        Returns:
            list[str]: Content converted from the JSON response as a list.
        """
        # This is an arbitraty number; a device title key from the response will be padded with tildes to be a line with this length
        device_title_len = 86
        devices = user_config.keys()

        all_lines = []
        for dvc in devices:
            lines_list = []
            # Current API response lines mostly don't have '\n' at the end, but lines from the txt
            # have. So add '\n' to make them more harmounious.
            for line in user_config[dvc]:
                if line == "\n":
                    lines_list.append(line)
                else:
                    lines_list.append(line + "\n")

            title_padding_len = round((device_title_len - len(dvc) - 2) / 2)
            all_lines.append("~" * title_padding_len + " " + dvc + " " + "~" * title_padding_len)
            all_lines.extend(lines_list)

        return all_lines
