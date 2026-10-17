import difflib

from conftee.models.differ_o import DifferO

# This script is designed to demonstrate that Python's difflib module has a 
# default similarity threshold of 75% for comparing sequences. 
# It shows that difflib will report differences between two lines 
# if they are above this similarity cutoff, by comparing pairs of lines with 
# varying degrees of similarity and highlighting the differences.

paragraph1 = "abcdefgh23\nabcdefg123"
paragraph2 = "abcdefgh56\nabcdefg456"

def compare_paragraphs(paragraph1, paragraph2):
    """
    Compares two paragraphs line by line.

    Parameters
    ----------
    paragraph1 : str
        The first paragraph
    paragraph2 : str
        The second paragraph

    Returns
    -------
    str
        The differences between the two paragraphs
    """
    lines1 = paragraph1.splitlines()
    lines2 = paragraph2.splitlines()
    differ = difflib.Differ()
    diff = list(differ.compare(lines1, lines2))
    return '\n'.join(diff)

def compare_lines_from_files(file_path_1, file_path_2):

    with open(file_path_1, 'r') as file:
        # Read the content
        file_content_1 = file.read()

    with open(file_path_2, 'r') as file:
        # Read the content
        file_content_2 = file.read()

    return compare_paragraphs(file_content_1, file_content_2)


diff = compare_paragraphs(paragraph1, paragraph2)
print("\nSimple run to test the oringinal Differ on two 2-line texts:")
print(diff)

print("\nSimple run to test the oringinal Differ on one section:")
diff = compare_lines_from_files('./examples/golden/test_file_one_section_bad.txt', './examples/user/test_file_one_section_bad.txt')
print(diff)


paragraph1 = "This is the {FIRST} sentence.\nThis is a second line.\nA first missing line.\nA second missing line.\n3rd line"
paragraph2 = "This is the first sentence.\nThis is a second line.\nA second missing line (depends on ratio).\n3rd li\nAn extra line."
differ_o = DifferO(cutoff=0.5)
result = differ_o.compare(paragraph1.splitlines(), paragraph2.splitlines())
joined = [line for line in result]
print("\nSimple run to test the changable ratio in DifferO:")
for line in joined:
    print(line.replace("\n", ""))

differ_o = DifferO(cutoff=0.5)
comp_res = differ_o.compare(paragraph1.splitlines(), paragraph2.splitlines())
df,_,_,_ = differ_o.seperate_line_ops(comp_res)
print(df)