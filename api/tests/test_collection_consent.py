from api.tests.test_api import auth, env, sample  # noqa: F401
from api.tests.conftest import all_samples


def test_collection_requires_opt_in_and_stops_after_withdrawal(env):
    client, clock, store = env
    pair = client.post('/api/pair/create').get_json()
    dashboard = auth(pair['dashboardToken'])
    device = auth(client.post('/api/pair/claim', json={'code': pair['pairingCode']}).get_json()['deviceToken'])
    def ingest():
        return client.post('/api/posture/ingest', json=sample(clock), headers=device)
    assert ingest().status_code == 403
    assert all_samples(store) == []
    assert client.put('/api/settings', json={'dataCollectionConsent': 'yes'}, headers=dashboard).status_code == 400
    assert ingest().status_code == 403
    assert client.put('/api/settings', json={'dataCollectionConsent': True}, headers=dashboard).status_code == 200
    assert ingest().status_code == 200
    # Unrelated settings updates preserve the choice.
    client.put('/api/settings', json={'sensitivity': 0.7}, headers=dashboard)
    assert client.get('/api/settings', headers=dashboard).get_json()['settings']['dataCollectionConsent'] is True
    before = len(all_samples(store))
    client.put('/api/settings', json={'dataCollectionConsent': False}, headers=dashboard)
    clock['t'] += 10000
    assert ingest().status_code == 403
    assert len(all_samples(store)) == before
