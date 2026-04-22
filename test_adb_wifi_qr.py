import sys
from unittest.mock import MagicMock

# Mock dependencies that are not installed in the environment
sys.modules["qrcode"] = MagicMock()
sys.modules["zeroconf"] = MagicMock()

import string
import adb_wifi_qr

def test_generate_name():
    """
    Test that generate_name returns a string in the format '14chars-6chars'
    consisting of alphanumeric characters.
    """
    name = adb_wifi_qr.generate_name()
    assert isinstance(name, str)

    # Check format: part1(14) - part2(6)
    parts = name.split("-")
    assert len(parts) == 2
    assert len(parts[0]) == 14
    assert len(parts[1]) == 6

    # Check character set
    charset = string.ascii_letters + string.digits
    for char in parts[0]:
        assert char in charset
    for char in parts[1]:
        assert char in charset

def test_generate_password():
    """
    Test that generate_password returns a string of 21 alphanumeric characters.
    """
    password = adb_wifi_qr.generate_password()
    assert isinstance(password, str)
    assert len(password) == 21

    # Check character set
    charset = string.ascii_letters + string.digits
    for char in password:
        assert char in charset

def test_generate_name_randomness():
    """
    Ensure multiple calls to generate_name produce different results.
    """
    names = {adb_wifi_qr.generate_name() for _ in range(100)}
    assert len(names) == 100

def test_generate_password_randomness():
    """
    Ensure multiple calls to generate_password produce different results.
    """
    passwords = {adb_wifi_qr.generate_password() for _ in range(100)}
    assert len(passwords) == 100
