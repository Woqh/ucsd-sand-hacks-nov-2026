import pytest

from api.tests.test_api import auth, env, paired, feed  # noqa: F401


@pytest.mark.parametrize('muted', [False, True])
def test_poor_posture_pushes_external_phone_after_threshold(env, monkeypatch, muted):
    client, clock, _ = env
    dashboard, sensor = paired(client)
    headers = auth(dashboard)
    client.put('/api/settings', headers=headers, json={
        'slouchThresholdSec': 5, 'cooldownSec': 120,
        'alertChannels': {'phone': not muted, 'desktop': False},
    })
    code = client.post('/api/push/web/receiver/pairing', headers=headers).get_json()['code']
    token = client.post('/api/push/web/receiver/claim', json={'code': code}).get_json()['receiverToken']
    subscription = {'endpoint': 'https://push.example/iphone', 'keys': {'p256dh': 'key', 'auth': 'secret'}}
    client.post('/api/push/web/receiver/subscribe', headers=auth(token), json=subscription)
    calls = []
    monkeypatch.setattr('api.push.dispatch.webpush.configured', lambda: True)
    def send(sub, title, body, **options):
        calls.append((sub, options))
        return True, 201, None
    monkeypatch.setattr('api.push.dispatch.webpush.send', send)

    status = client.get('/api/push/phone/status', headers=headers).get_json()
    assert status['receivers'] == 1 and status['webPushConfigured']
    assert status['enabled'] is (not muted) and status['collectionAllowed']
    assert client.get('/api/push/phone/status', headers=auth(token)).status_code == 401
    feed(client, sensor, clock, 5, 'GOOD', 0.1)
    feed(client, sensor, clock, 4, 'SLOUCHING', 0.9)
    assert calls == []  # no vibration for a momentary posture change
    feed(client, sensor, clock, 3, 'SLOUCHING', 0.9)
    assert len(calls) == (0 if muted else 1)
    if calls:
        assert calls[0][0]['endpoint'] == subscription['endpoint']
        assert calls[0][1]['url'] == '/receive'
    feed(client, sensor, clock, 10, 'SLOUCHING', 0.9)
    assert len(calls) == (0 if muted else 1)  # cooldown prevents repeated buzzes
    feed(client, sensor, clock, 10, 'GOOD', 0.1)
    assert len(calls) == (0 if muted else 1)
