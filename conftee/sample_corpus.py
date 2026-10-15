"""Infrastructure prefixes for the sample configs this repo ships with.

The engine takes these as an argument rather than owning them: in a real
deployment they come from whatever the network's source of truth is, usually an
API response. They live here because they describe `golden_config_files/` and
`user_config_files/`, not the engine, and the sample corpus is the only thing
they are correct for.

The variable names on the right of each entry must match the schema's, since
`_determine_correct_values` writes the computed ranges straight into the
correct-values table under those names.

Note this is not the same kind of file as `schemas/cisco-campus.yaml`, despite
describing the same network. The schema is a vocabulary: it says `FWGLUE_Prefix`
is an IPv4 value constrained to the infra pool, which holds for every config
written in that dialect. This file records what one network's prefix happens to
be, which holds for nothing else. Two deployments sharing the dialect share the
schema byte for byte and share none of these values, so they are kept apart.

It sits inside the package only because `main.py` is a demo driver over the
sample corpus and needs the data at run time. It belongs with that corpus rather
than with the engine, and moves with it when the corpus is reorganized; see
docs/repurposing-plan.md section 3.
"""

SAMPLE_INFRA_PREFIXES = {
    # Equivalent to FWGLUE_Prefix.
    "TEST_CONTEXT_1-FWGLUE": {"prefix": "10.45.54.24/29", "prefix_type": "fwglue"},
    # Equivalent to Vrfglue_prefix.
    "TEST_O-VRFGLUE=TEST-TEST_VRF_1": {"prefix": "10.45.54.208/29", "prefix_type": "vrfglue"},
    "TEST U-TEST_PREFIX_1=TEST_VRF_1": {"prefix": "10.45.54.24/29", "prefix_type": "user"},
    "TEST U-TEST_PREFIX_2=TEST_VRF_1": {"prefix": "10.45.54.24/29", "prefix_type": "user"},
}
