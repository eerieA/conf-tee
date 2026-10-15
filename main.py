from colored import fg, bg, attr

from conftee.models.config_compare import ConfigCompare
from conftee.models.extract import Extract

from conftee.models.outline import Outline
from conftee.models.gen_summary import GenSummary
from conftee.utils.read_config import ReadConfig
from conftee.utils import schema as schema_module

success_color = fg("green")
attention_color = fg("blue")
reset_color = attr("reset")

SCHEMA_PATH = "./conftee/schemas/cisco-campus.yaml"
GOLDEN_DIR = "./golden_config_files/"
USER_DIR = "./user_config_files/"
# TEST_FILE_NAME = 'test_file_one_line_bad.txt'
# TEST_FILE_NAME = 'test_file_one_section_bad.txt'
# TEST_FILE_NAME = 'test_file_structure_good.txt'
TEST_FILE_NAME = "test_file_structure_bad.txt"
# TEST_FILE_NAME = 'test_file_two_devices.txt'
# TEST_FILE_NAME = 'test_Building router is HSRP router pair, FW context router is VSS router pair'


# Main entry function


def main():

    ################## Console UI handling ##################

    print("Here are all current golden config files.\nChoose the one to compare against:")
    input_file_name = ReadConfig.prompt_select_file(GOLDEN_DIR, "Enter the golden config file's name: ")
    golden_file, user_file = "", ""
    if len(input_file_name) > 0 and ReadConfig.is_file_in_dir(input_file_name, USER_DIR):
        print("Automatically choosing the same named file in user config file folder...")
        golden_file = GOLDEN_DIR + input_file_name
        user_file = USER_DIR + input_file_name
    else:
        print(
            f'File not found in golden config file folder or user config file folder. \n\tMaybe forgot the .txt extension or the file is not there? \n\tNo worries. Will use test file pair "{TEST_FILE_NAME}".'
        )
        golden_file = GOLDEN_DIR + TEST_FILE_NAME
        user_file = USER_DIR + TEST_FILE_NAME

    print(success_color + "File read was successful." + reset_color)

    ################## Start main functionality ##################

    # Load
    file_content_1 = ReadConfig.read_config_from_txt(golden_file)
    file_content_2 = ReadConfig.read_config_from_txt(user_file)

    # Prepare
    extractGolden, extractUser = Extract._extract_structs(file_content_1, file_content_2)
    extractData = (extractGolden, extractUser)

    outlineGolden = Outline(file_content_1, extractGolden, True)
    outlineUser = Outline(file_content_2, extractUser, False)
    outlineData = (outlineGolden, outlineUser)

    # Calculate
    schema = schema_module.load(SCHEMA_PATH)
    comparer = ConfigCompare(extractData, outlineData, schema)
    comparer_results = comparer.calculate_diff(infra_prefixes=None)

    # Generate reports
    summ_generator = GenSummary(schema)
    summary, diff_result_df, json_report = summ_generator.generate_reports(
        outlineGolden,
        outlineUser,
        comparer_results,
    )

    # Output reports
    print(json_report)
    diff_result_df.to_csv("out.csv", index=False)
    print('Tabular visualization of the result is also written into "./out.csv". Please read it as needed.')


main()
