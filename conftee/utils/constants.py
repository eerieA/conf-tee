"""Syntax constants the engine owns.

These describe how a value or a block is *written*, not what any particular
network calls things, so they are the same for every user and belong in the
code. The vocabulary (which variables exist, what each looks like, which
arithmetic and pool each belongs to) is declared per deployment in a schema
instead; see `conftee/schemas/cisco-campus.yaml` and `utils/schema.py`.
"""

# GENERAL_IPV4_REGEX is for detecting general IPv4 addresses as a whole, without restricting 0-255 for octets
GENERAL_IPV4_REGEX = r"(?:[0-9]{1,3}\.){3}[0-9]{1,3}"
GENERAL_CIDR_MASK_REGEX = r"\/(3[0-2]|[1-2]{0,1}[0-9])"

BLOCK_TYPE_DEVICE, BLOCK_TYPE_SECTION = "d", "s"
