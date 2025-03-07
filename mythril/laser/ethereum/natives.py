"""This nodule defines helper functions to deal with native calls."""

import hashlib
import logging
from typing import List

import blake2b
import coincurve
import py_ecc.optimized_bn128 as bn128
from eth._utils.blake2.coders import extract_blake2b_parameters
from eth._utils.bn128 import validate_point
from eth_utils import ValidationError, big_endian_to_int, int_to_big_endian
from py_ecc.secp256k1 import N as secp256k1n
from py_ecc.secp256k1 import ecdsa_raw_recover
from rlp.utils import ALL_BYTES

from mythril.laser.ethereum.state.calldata import BaseCalldata, ConcreteCalldata
from mythril.laser.ethereum.util import extract32, extract_copy
from mythril.support.support_utils import sha3, zpad

log = logging.getLogger(__name__)


def encode_int32(v):
    return v.to_bytes(32, byteorder="big")


def safe_ord(value):
    if isinstance(value, int):
        return value
    else:
        return ord(value)


def int_to_32bytearray(i):
    o = [0] * 32
    for x in range(32):
        o[31 - x] = i & 0xFF
        i >>= 8
    return o


def ecrecover_to_pub(rawhash, v, r, s):
    if hasattr(coincurve, "PublicKey"):
        try:
            pk = coincurve.PublicKey.from_signature_and_message(
                zpad(bytes(int_to_32bytearray(r)), 32)
                + zpad(bytes(int_to_32bytearray(s)), 32)
                + ALL_BYTES[v - 27],
                rawhash,
                hasher=None,
            )
            pub = pk.format(compressed=False)[1:]
        except BaseException:
            pub = b"\x00" * 64
    else:
        result = ecdsa_raw_recover(rawhash, (v, r, s))
        if result:
            x, y = result
            pub = encode_int32(x) + encode_int32(y)
        else:
            raise ValueError("Invalid VRS")
    assert len(pub) == 64
    return pub


class NativeContractException(Exception):
    """An exception denoting an error during a native call."""

    pass


def ecrecover(data: List[int]) -> List[int]:
    """

    :param data:
    :return:
    """
    # TODO: Add type hints
    try:
        bytes_data = bytearray(data)
        v = extract32(bytes_data, 32)
        r = extract32(bytes_data, 64)
        s = extract32(bytes_data, 96)
    except TypeError:
        raise NativeContractException

    message = b"".join([ALL_BYTES[x] for x in bytes_data[0:32]])
    if r >= secp256k1n or s >= secp256k1n or v < 27 or v > 28:
        return []
    try:
        pub = ecrecover_to_pub(message, v, r, s)
    except Exception as e:
        log.debug("An error has occurred while extracting public key: " + str(e))
        return []
    o = [0] * 12 + [x for x in sha3(pub)[-20:]]
    return list(bytearray(o))


def sha256(data: List[int]) -> List[int]:
    """

    :param data:
    :return:
    """
    try:
        bytes_data = bytes(data)
    except TypeError:
        raise NativeContractException
    return list(bytearray(hashlib.sha256(bytes_data).digest()))


def ripemd160(data: List[int]) -> List[int]:
    """

    :param data:
    :return:
    """
    try:
        bytes_data = bytes(data)
    except TypeError:
        raise NativeContractException
    digest = hashlib.new("ripemd160", bytes_data).digest()
    padded = 12 * [0] + list(digest)
    return list(bytearray(bytes(padded)))


def identity(data: List[int]) -> List[int]:
    """

    :param data:
    :return:
    """
    return data


def mod_exp(data: List[int]) -> List[int]:
    """
    TODO: Some symbolic parts can be handled here
    Modular Exponentiation
    :param data: Data with <length_of_BASE> <length_of_EXPONENT> <length_of_MODULUS> <BASE> <EXPONENT> <MODULUS>
    :return: modular exponentiation
    """
    bytes_data = bytearray(data)
    baselen = extract32(bytes_data, 0)
    explen = extract32(bytes_data, 32)
    modlen = extract32(bytes_data, 64)
    if baselen == 0:
        return [0] * modlen
    if modlen == 0:
        return []

    first_exp_bytes = extract32(bytes_data, 96 + baselen) >> (8 * max(32 - explen, 0))
    while first_exp_bytes:
        first_exp_bytes >>= 1

    base = bytearray(baselen)
    extract_copy(bytes_data, base, 0, 96, baselen)
    exp = bytearray(explen)
    extract_copy(bytes_data, exp, 0, 96 + baselen, explen)
    mod = bytearray(modlen)
    extract_copy(bytes_data, mod, 0, 96 + baselen + explen, modlen)
    if big_endian_to_int(mod) == 0:
        return [0] * modlen
    o = pow(big_endian_to_int(base), big_endian_to_int(exp), big_endian_to_int(mod))
    return [safe_ord(x) for x in zpad(int_to_big_endian(o), modlen)]


def ec_add(data: List[int]) -> List[int]:
    bytes_data = bytearray(data)
    x1 = extract32(bytes_data, 0)
    y1 = extract32(bytes_data, 32)
    x2 = extract32(bytes_data, 64)
    y2 = extract32(bytes_data, 96)
    try:
        p1 = validate_point(x1, y1)
        p2 = validate_point(x2, y2)
    except ValidationError:
        return []
    if p1 is False or p2 is False:
        return []
    o = bn128.normalize(bn128.add(p1, p2))
    return [safe_ord(x) for x in (encode_int32(o[0].n) + encode_int32(o[1].n))]


def ec_mul(data: List[int]) -> List[int]:
    bytes_data = bytearray(data)
    x = extract32(bytes_data, 0)
    y = extract32(bytes_data, 32)
    m = extract32(bytes_data, 64)
    try:
        p = validate_point(x, y)
    except ValidationError:
        return []
    if p is False:
        return []
    o = bn128.normalize(bn128.multiply(p, m))
    return [safe_ord(c) for c in (encode_int32(o[0].n) + encode_int32(o[1].n))]


def ec_pair(data: List[int]) -> List[int]:
    if len(data) % 192:
        return []

    zero = (bn128.FQ2.one(), bn128.FQ2.one(), bn128.FQ2.zero())
    exponent = bn128.FQ12.one()
    bytes_data = bytearray(data)
    for i in range(0, len(bytes_data), 192):
        x1 = extract32(bytes_data, i)
        y1 = extract32(bytes_data, i + 32)
        x2_i = extract32(bytes_data, i + 64)
        x2_r = extract32(bytes_data, i + 96)
        y2_i = extract32(bytes_data, i + 128)
        y2_r = extract32(bytes_data, i + 160)
        p1 = validate_point(x1, y1)
        if p1 is False:
            return []
        for v in (x2_i, x2_r, y2_i, y2_r):
            if v >= bn128.field_modulus:
                return []
        fq2_x = bn128.FQ2([x2_r, x2_i])
        fq2_y = bn128.FQ2([y2_r, y2_i])
        if (fq2_x, fq2_y) != (bn128.FQ2.zero(), bn128.FQ2.zero()):
            p2 = (fq2_x, fq2_y, bn128.FQ2.one())
            if not bn128.is_on_curve(p2, bn128.b2):
                return []
        else:
            p2 = zero
        if bn128.multiply(p2, bn128.curve_order)[-1] != bn128.FQ2.zero():
            return []
        exponent *= bn128.pairing(p2, p1, final_exponentiate=False)
    result = bn128.final_exponentiate(exponent) == bn128.FQ12.one()
    return [0] * 31 + [1 if result else 0]


def blake2b_fcompress(data: List[int]) -> List[int]:
    """
    blake2b hashing
    :param data:
    :return:
    """
    try:
        parameters = extract_blake2b_parameters(bytes(data))
    except ValidationError as v:
        logging.debug("Invalid blake2b params: {}".format(v))
        return []
    return list(bytearray(blake2b.compress(*parameters)))


PRECOMPILE_FUNCTIONS = (
    ecrecover,
    sha256,
    ripemd160,
    identity,
    mod_exp,
    ec_add,
    ec_mul,
    ec_pair,
    blake2b_fcompress,
)

PRECOMPILE_COUNT = len(PRECOMPILE_FUNCTIONS)


def native_contracts(address: int, data: BaseCalldata) -> List[int]:
    """Takes integer address 1, 2, 3, 4.

    :param address:
    :param data:
    :return:
    """

    if not isinstance(data, ConcreteCalldata):
        raise NativeContractException
    concrete_data = data.concrete(None)
    try:
        return PRECOMPILE_FUNCTIONS[address - 1](concrete_data)
    except TypeError:
        raise NativeContractException
