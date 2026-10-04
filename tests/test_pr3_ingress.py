"""Verify wire preservation and version routing without AWS or network calls."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def gateway_class():
    filename = Path(__file__).parents[1] / 'src/ocpp-gateway-container/gateway.py'
    spec = importlib.util.spec_from_file_location('gateway_under_test', filename)
    module = importlib.util.module_from_spec(spec)
    modules = {'asyncio_mqtt': SimpleNamespace(Client=type('Client', (), {'__init__': lambda self, *a, **kw: None})),
               'boto3': SimpleNamespace(resource=MagicMock())}
    environment = {'AWS_REGION': 'us-east-2', 'DYNAMODB_CHARGE_POINT_TABLE': 'test',
                   'IOT_ENDPOINT': 'test', 'IOT_PORT': '8883'}
    with patch.dict(sys.modules, modules), patch.dict(os.environ, environment):
        spec.loader.exec_module(module)
        with patch.object(module.Gateway, 'create_ssl_context'), patch.object(module.Gateway, 'charge_point_exists', return_value=True):
            yield module.Gateway


@pytest.mark.parametrize('raw', ['[2,"a","Heartbeat",{}]', '[3,"b",{}]',
                                '[4,"c","InternalError","detail",{"field":"x"}]',
                                ' [2, "d", "Heartbeat", {}] ', 'invalid JSON'])
def test_201_preserves_original_frame_and_connection_evidence(gateway_class, raw):
    websocket = SimpleNamespace(subprotocol='ocpp2.0.1', recv=AsyncMock(side_effect=[raw, RuntimeError('finished')]))
    gateway = gateway_class('station', websocket)
    gateway.publish = AsyncMock()
    with pytest.raises(RuntimeError, match='finished'):
        asyncio.run(gateway.forward('station/in'))
    call = gateway.publish.call_args
    assert call.args == ('station/v201/in',)
    assert call.kwargs['qos'] == 1
    envelope = json.loads(call.kwargs['payload'])
    assert envelope['message'] == raw
    assert envelope['protocolVersion'] == 'ocpp2.0.1'
    assert envelope['protocolVersionSource'] == 'websocket'
    assert envelope['connectionId'] == gateway.connection_id
    assert envelope['direction'] == 'inbound'
    assert envelope['receivedAt'].endswith('+00:00')


@pytest.mark.parametrize('protocol', ['ocpp1.6', 'ocpp2.0'])
def test_legacy_wire_and_topic_remain_unchanged(gateway_class, protocol):
    raw = '[2,"id","Heartbeat",{}]'
    websocket = SimpleNamespace(subprotocol=protocol, recv=AsyncMock(side_effect=[raw, RuntimeError('finished')]))
    gateway = gateway_class('station', websocket)
    gateway.publish = AsyncMock()
    with pytest.raises(RuntimeError):
        asyncio.run(gateway.forward('station/in'))
    gateway.publish.assert_awaited_once_with('station/in', payload=raw)


def test_new_connection_gets_new_identity(gateway_class):
    websocket = SimpleNamespace(subprotocol='ocpp2.0.1')
    assert gateway_class('station', websocket).connection_id != gateway_class('station', websocket).connection_id
