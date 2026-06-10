import pytest
import json

def test_status_endpoint(client):
    """Test standard status endpoint."""
    res = client.get('/status')
    assert res.status_code == 200
    data = res.get_json()
    assert data['ok'] is True
    assert 'attendance_window' in data

def test_quantum_status_endpoint(client):
    """Test quantum security status endpoint."""
    res = client.get('/quantum/status')
    assert res.status_code == 200
    data = res.get_json()
    assert 'kem_algorithm' in data
    assert 'signature_scheme' in data

def test_attendance_list_endpoint(client):
    """Test attendance list returns a records array."""
    res = client.get('/attendance/list')
    assert res.status_code == 200
    data = res.get_json()
    assert 'records' in data
    assert isinstance(data['records'], list)
