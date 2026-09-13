# conf-tee

## Overview
This tool is designed to compare generated configuration file against a maually defined standard format. Differences between the two files are aggregated into a table for human review, and into a JSON report for integration use.

## Project history

This tool was built for a university network operations simulation project and has since been
retired; it is published here in a generalized, sanitized form.

| Period | What happened |
|---|---|
| Aug 2023 – Dec 2023 | **v1** written by a previous student developer. Not included in this repository; see [docs/v1-retrospective.md](./docs/v1-retrospective.md) for its architecture and the lessons taken from it. |
| Apr 2024 – Jul 2024 | **v2**, the code in this repository: a full rewrite into the layered design described in [docs/architecture.md](./docs/architecture.md). |
| (undated) | Retired from production use; no longer deployed anywhere. |
| Sep 2026 | Repurposing for public release begins: predecessor code removed, organization- and person-identifying sample data replaced, regression tests added. See [docs/repurposing-plan.md](./docs/repurposing-plan.md). |

Both the version number (0.1.5) and the requirements list below date from that original development. The initial commit is when this repository was created for publication; it says nothing about how long the tool took to write.

## Table of Contents

- [Client requirements](#client-requirements)
- [Environment](#environment)
- [How to Run the Tool (Local Standalone)](#how-to-run-the-tool-local-standalone)
  - [1 Preparing the Config Files](#1-preparing-the-config-files)
  - [2 Starting and Selecting the Golden Config](#2-starting-and-selecting-the-golden-config)
  - [3 Selecting the User Config](#3-selecting-the-user-config)
  - [4 Result](#4-result)
- [How to Run the Tool (Integration)](#how-to-run-the-tool-integration)
- [Addendum A (For devs): Extra documentation](#addendum-a-documentations-for-devs)
- [Addendum B (For devs): Running the tests](#addendum-b-running-the-tests)
- [Addendum C (For devs): Dev tools](#addendum-c-dev-tools-notes)

## Client requirements:
1. Compare user-defined configurations against a standard format (golden config).
    - ✓ Validate the format of values for variables within "{}" in golden config, based on regular expressions.
    - ✓ Identify variables that do not have corresponding values.
    - ✓ Identify missing/extra lines in the user config.
    - ✓ Identify device & section blocks in the user config, and missing/extra blocks.
    - ✓ Identify inconsistent values for variables that should have the same value in one section or throughout a config.
    - ✓ Evaluate numerical calculations on IP values, such as {Vrfglue_prefix_1st_IP}+1.
    - ✓ Validate values for variables that should be in the same range, such as FWGLUE_Prefix with FWGLUE_Prefix_last_IP.
    - ✓ Catch differences in non-variable commands.
    - Detect structure relational anomalies, such as inconsistent numbers of downlink portchannels and downlink device blocks.
2. An interactive way for a human reviewer to select input configs and view results (for standalone usage).
3. A module interface for collaboration with outside callers (for integration).
4. A readable error report for human review.

## Environment
Python 3.9 or newer. From the repository root:

```
python -m venv .venv
.venv\Scripts\activate.bat          # Windows cmd; use activate.ps1 in PowerShell,
                                     # or source .venv/bin/activate on Linux/macOS
python -m pip install -r requirements.txt
```

Dependencies are declared as lower bounds rather than exact pins, so the install
picks wheels built for whichever Python you are on. Pinning exact versions ties
the project to the interpreter versions current when those versions shipped.

- Note: Pandas is a real dependency of the current code: `differ_o`, `section_comparer`, `gen_summary` and `config_compare` all build and read DataFrames, so installing without it will not work. But that is a design choice, not a requirement of the problem. The DataFrame is used as the intermediate structure passed between those modules, and for readable output such as `out.csv`. What it is *not* used for is anything pandas is actually good at: there are no joins, group-bys or vectorized numerics in the pipeline, and every `.apply` is a row-wise Python lambda, which is a loop by another name. Any similarly shaped record structure plus hand-written access logic would produce identical results. Swapping it out is a contained refactor of those four modules, not a redesign.

## How to Run the Tool (Local Standalone)

### 1 Preparing the Config Files
1. Double check golden configuration content syntaxes:
    - File must contain at least one device title and one section title;
    - File must start with a "~", though having some white spaces beore it is fine;
    - Every device title line must start with at least 3 tildes `~~~` and match a format like "~~~ device name ~~~";
    - Every section start line should start with exactly the string `! #` and match a format like "! # CONTEXT START #", but an end line is optional;
    - Some device names need to be 100% accurate, for example "al1asa" in golden file and "al1asaX" in user file will cause a structure mismatch;
    - Variables should be in curly brackets, like {User_prefix};
    - Variable names are **case sensitive**, meaning if {User_prefix} works then {User_Prefix} would cause errors.
    - Algebraic expressions should be in nested curly brackets, and operand can only be integers, like {{Vrfglue_prefix_1st_IP}+1}. <br>
    Example:

          ~~~~~~~ site01-hub1 ~~~~~
          ! ########### VRF START ########### 
            ip address {Vrfglue_prefix_1st_IP} {Vrfglue_prefix_netmask} standby {{Vrfglue_prefix_1st_IP}+1}
    
2. Open the folder where the Configuration Comparison Tool is located. 
3. Locate two sub-folders: `./user_config_files` and `./golden_config_files`. 
4. Create both configuration text files for comparison in the respective folders: <br>
   Place user configuration files inside user_config_files. <br>
   Place golden configuration files inside golden_config_files. <br>
   Keep both file names as the same.

### 2 Starting and Selecting the Golden Config
1. Execute the `main.py` script.
2. Upon running the tool, a list of available golden configuration files will be presented in your chosen CLI.
3. Input the file name (with extension) of your chosen golden configuration file.
- Note: Currently works correctly for these standalone files:
    - *test_file_one_device.txt*
    - *test_file_one_line_bad.txt*
    - *test_file_one_section_bad.txt*
    - *test_file_structure_bad.txt*
    - *test_file_structure_good.txt*
    - *test_file_two_devices.txt*
    - *test_Building router is HSRP router pair, FW context router is VSS router pair.txt*
    - *add a FW context connected to HSRP router pair.txt*
    - *add a FW context connected to VSS router pair.txt*
    - ...
    - *add an IB wireless prefix on a VRF in wireless  rt-hsrp different context rt-vss wireless rt has no vrf incl ip helper.txt*
    - *add an IB wireless prefix on a VRF in wireless  rt-hsrp different context rt-vss wireless rt has vrf incl ip helper.txt*
    
    Feel free to try others of your own, but there might be errors and/or failures.

### 3 Selecting the User Config
1. It will be searched using the same name in the user_config_files folder. The program will run a test file pair if a user configuration file is not found.


### 4 Result
1. Wait for the tool to finish the procedure.
2. Review the JSON report printed in the terminal.
3. (Optional) Review the diff results dataframe (table) printed into an out.csv under the root folder. <br>


## How to Run the Tool (Integration)

*Note: Currently using `poetry` for packaging, but importer program does not have to have poetry in venv. This workflow might change later since this packaging method is still under probation.*

Importing and usage steps:
1. Install the module from a local build (`poetry build`, then `pip install` the produced wheel).
2. Use `from conftee.models.config_compare import ConfigCompare` etc to import the main classes.
3. Pass in user config with proper native Python data structures to the read_config_from_response(.) function.
4. Pass in golden config from a txt file, and then call calculate_diff() on them. <br>
    For example:
      ```
      import aiohttp, asyncio
      from conftee.models.config_compare import ConfigCompare
      from conftee.models.extract import Extract
      from conftee.models.outline import Outline
      from conftee.models.gen_summary import GenSummary
      from conftee.utils.read_config import ReadConfig
      ...

      body, status = await get(path="/api/v1/view/network/biss01/configs", auth=ADMIN_JWT)

      # This should be a dict[str, list[str]]
      user_json_obj = body['results'][0]
      user_content = ReadConfig.read_config_from_response(user_json_obj)
      golden_content = ReadConfig.read_config_from_txt("./golden_config_files/sample_golden.txt")

      extractGolden, extractUser = Extract._extract_structs(golden_content, user_content)
      extractData = (extractGolden, extractUser)

      outlineGolden = Outline(golden_content, extractGolden, True)
      outlineUser = Outline(user_content, extractUser, False)
      outlineData = (outlineGolden, outlineUser)

      comparer = ConfigCompare(extractData, outlineData)
      comparer_results = comparer.calculate_diff()

      summ_generator = GenSummary()
      summary, diff_result_df, json_report = summ_generator.generate_reports(
        outlineGolden,
        outlineUser,
        comparer_results,
        )
      print(json_report)

      # In summary, The 1st child list's 1st element is value mismatch count
      assert summary[0][0] == 0, f"Expected 0 {summary[0][1]}, but got {summary[0][0]}"
      ```
    *Note: The above code is for rough demonstration, it might not actually work.*
    
    The output *json_report* would be in this format:
      ```
      {
      'site01-hub1': {
                'vrf': [
                          {
                            'mismatch': {
                                'expected': 'ip VRF NOVA01-VPN',
                                'actual': 'ip VRF NOVA01-VPN-1'
                            }
                          }
                        ]
                  }
      'bldg07-sw01-32': {
                ...
                  }
      }
      ```
    The output *diff_result_df* would be in this format:
    | Line num 1 | Line in 1                                                        | Line num 2 | Line in 2                                | diff_result                                             | variables                                              | is expression                      | values                             | Value mistaches |
    |------------|------------------------------------------------------------------|------------|------------------------------------------|---------------------------------------------------------|--------------------------------------------------------|------------------------------------|------------------------------------|-----------------|
    | 1          | ~~~~~~~~~  al1asa FW context ~~~~~~~~~~                          | 1          | ~~~~~~~~~  al1asa FW context ~~~~~~~~~~  | ('equal-device-title', 0, 0, 0, 72)                     | []                                                     | []                                 | []                                 | 0               |
    | ...        | ...                                                              | ...        | ...                                      | ...                                                     | ...                                                    | ...                                | ...                                | ...             |
    | 244        |   description {FW_context_name}-FWGLUE                           | 243        |   description NOVA22-FWGLUE              | [('equal', 0, 14, 0, 14), ('replace-var', 14, 31...     | ['FW_context_name']                                    | [False]                            | ['NOVA2']                          | 1               |
    | 245        |   mtu 9216                                                       | 244        |   mtu 9216                               | [('equal', 0, 10, 0, 10), ('Line num 1', 245, 0, 0, 0)] | []                                                     | []                                 | []                                 | 0               |
    | 246        |   ip address {{FWGLUE_Prefix_last_IP}-1} {FWGLUE_Prefix_netmask} | 245        |   ip address 10.45.54.29 255.255.255.248 | [('equal', 0, 13, 0, 13), ('replace-var', 13, 40,...    | ['{FWGLUE_Prefix_last_IP}-1', 'FWGLUE_Prefix_netmask'] | ['{FWGLUE_Prefix_last_IP}', False] | ['10.45.54.29', '255.255.255.248'] | 0               |
    | 247        |   standby ip {FWGLUE_Prefix_last_IP}                             | 246        |   standby ip 10.45.54.30                 | [('equal', 0, 13, 0, 13), ('replace-var', 13, 36...     | ['FWGLUE_Prefix_last_IP']                              | [False]                            | ['10.45.54.30']                    | 0               |
    | 248        |   standby preempt                                                | 247        |   standby preempt                        | [('equal', 0, 17, 0, 17), ('Line num 1', 248, 0, 0, 0)] | []                                                     | []                                 | []                                 | 0               |
    | ...        | ...                                                              | ...        | ...                                      | ...                                                     | ...                                                    | ...                                | ...                                | ...             |


***
#### Addendum A: Documentations for Devs
See [docs/v1-retrospective.md](./docs/v1-retrospective.md) for an analysis of the
predecessor implementation and the reasons for the rewrite.
See [docs/architecture.md](./docs/architecture.md) for the class/pipeline diagram.

#### Addendum B: Running the tests

From a virtual environment with the project's dependencies installed (see
[Environment](#environment)), add pytest and run it:

```
python -m pip install pytest
python -m pytest
```

Prefer `python -m pip` and `python -m pytest` over bare `pip` and `pytest`. The
`-m` form resolves through the interpreter you are actually running, so it cannot
silently act on a different Python than the one you intend.

The package does not need to be installed first. `pyproject.toml` sets
`pythonpath = ["."]`, which puts the repository root on `sys.path` so
`import conftee` resolves during development.

There are two suites, and they answer different questions.

`tests/test_regression.py` runs all 63 golden/user config pairs through the full
pipeline and compares the result against recorded summary counts and report
hashes in `tests/fixtures/baseline.json`. The baseline was generated from the
engine's own output, so these tests assert that behavior has not *changed*, not
that it is correct. A failure here means something shifted; investigate the
change rather than regenerating the baseline.

The same file also holds `test_no_identifying_strings`, which scans the sample
configs and `docs/` for identifiers that were removed when this repository was
published. It stores them as salted hashes rather than plaintext, so the check
can run without the names being present.

`tests/test_schema_equivalence.py` covers the schema work in progress. It pins
`conftee/schemas/cisco-campus.yaml` against the hardcoded constants it was
transcribed from, so a mistake in the schema fails with the name of the offending
variable instead of showing up later as a changed report. It is scaffolding: once
the engine reads the schema and the constants modules are gone, this file goes
with them. See [docs/repurposing-plan.md](./docs/repurposing-plan.md).

Useful variations:

```
python -m pytest tests/test_regression.py   # one suite
python -m pytest -k schema                 # tests matching a name
python -m pytest -x                        # stop at the first failure
python -m pytest -q                        # one line per file instead of per test
```

#### Addendum C: Dev tools notes
There are some independent tool scripts in ./dev_tools folder, for one past dev's personal use. So delete them as needed.

1. print_regexes_from_client.py: Read a txt file containing regexes from the client and print them as a prettified Python dict, for pasting into the conftee\utils\constants.py. Just to save some manual formatting time.

3. simple_difflib_run.py: Some simple run using the built-in difflib library and the slighly overriden Diiffer O class in this project, to show their differences.