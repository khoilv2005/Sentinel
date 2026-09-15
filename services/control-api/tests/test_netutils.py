import pytest
from app.netutils import classify_device, parse_private_network

def test_private_network_allowed():
    assert str(parse_private_network("192.168.1.0/24")) == "192.168.1.0/24"

def test_public_network_rejected():
    with pytest.raises(ValueError):
        parse_private_network("8.8.8.0/24")

def test_classification():
    assert classify_device([445, 3389]) == "windows"
    assert classify_device([8006]) == "hypervisor"
    assert classify_device([9100]) == "printer"
    assert classify_device([22]) == "server"
