"""Offline query/graph checks; native Langflow execution is validated separately."""
import copy
import json
import pathlib
import unittest
import uuid

import jq

ROOT = pathlib.Path(__file__).resolve().parent
FLOW = json.loads((ROOT / 'Odds Sample Audit.json').read_text())
NODES = {node['data']['type']: node for node in FLOW['data']['nodes'] if node['type'] == 'genericNode'}
QUERY = NODES['DataOperations']['data']['node']['template']['query']['value']
FIXTURE = json.loads((ROOT / 'synthetic-odds.json').read_text())


def audit(fixture, status=200):
    return jq.compile(QUERY).input({'status_code': status, 'result': fixture}).first()


class OddsSampleAuditTests(unittest.TestCase):
    def setUp(self):
        self.fixture = copy.deepcopy(FIXTURE)

    def test_stable_identity_and_required_flow_metadata(self):
        self.assertEqual(FLOW['id'], 'b4d95386-7c85-5601-8e02-ecefee6c756e')
        identifier = uuid.UUID(FLOW['id'])
        self.assertEqual(str(identifier), FLOW['id'])
        self.assertEqual(identifier.version, 5)
        self.assertEqual(FLOW['name'], 'Odds Sample Audit')
        for field in ['name', 'description']:
            self.assertIsInstance(FLOW[field], str)
            self.assertTrue(FLOW[field].strip())
        self.assertIsInstance(FLOW['tags'], list)
        self.assertTrue(FLOW['tags'])
        self.assertTrue(all(isinstance(tag, str) and tag.strip() for tag in FLOW['tags']))

    def test_known_complete_incomplete_and_ambiguous_groups(self):
        result = audit(self.fixture)
        self.assertEqual((result['event_count'], result['complete_markets'], result['incomplete_or_ambiguous_markets'], result['missing_source_timestamps']), (1, 1, 2, 1))
        self.assertFalse(result['market_checks'][2]['market_complete'])
        self.assertEqual(result['market_checks'][2]['h2h_group_count'], 2)

    def test_source_prices_and_timestamps_unchanged(self):
        book = self.fixture['events'][0]['bookmakers'][0]
        result = audit(self.fixture)['market_checks'][0]
        self.assertEqual(result['source_last_update'], book['last_update'])
        self.assertEqual(result['outcomes'], book['markets'][0]['outcomes'])

    def test_missing_timestamp_is_not_inferred(self):
        result = audit(self.fixture)['market_checks'][1]
        self.assertIsNone(result['source_last_update'])
        self.assertFalse(result['timestamp_present'])

    def test_timestamp_presence_is_not_freshness_or_validity(self):
        self.fixture['events'][0]['bookmakers'][0]['last_update'] = 'not-a-date'
        result = audit(self.fixture)
        self.assertEqual(result['market_checks'][0]['source_last_update'], 'not-a-date')
        self.assertIn('does not establish validity or freshness', result['timestamp_note'])

    def test_empty_events_is_valid(self):
        self.fixture['events'] = []
        result = audit(self.fixture)
        self.assertEqual(result['event_count'], 0)
        self.assertEqual(result['market_checks'], [])

    def test_duplicate_outcome_invalidates_market(self):
        outcomes = self.fixture['events'][0]['bookmakers'][0]['markets'][0]['outcomes']
        outcomes.append(copy.deepcopy(outcomes[0]))
        self.assertFalse(audit(self.fixture)['market_checks'][0]['market_complete'])

    def test_duplicate_bookmaker_invalidates_both_entries(self):
        books = self.fixture['events'][0]['bookmakers']
        books.append(copy.deepcopy(books[0]))
        result = audit(self.fixture)['market_checks']
        self.assertFalse(result[0]['market_complete'])
        self.assertFalse(result[-1]['market_complete'])

    def test_wrong_team_invalidates_market(self):
        self.fixture['events'][0]['bookmakers'][0]['markets'][0]['outcomes'][0]['name'] = 'Unrelated Team'
        self.assertFalse(audit(self.fixture)['market_checks'][0]['market_complete'])

    def test_numeric_source_price_required(self):
        for bad in [None, '110', True]:
            with self.subTest(price=bad):
                fixture = copy.deepcopy(self.fixture)
                fixture['events'][0]['bookmakers'][0]['markets'][0]['outcomes'][0]['price'] = bad
                self.assertFalse(audit(fixture)['market_checks'][0]['market_complete'])

    def test_three_way_market_accepts_explicit_draw(self):
        self.fixture['events'][0]['bookmakers'][0]['markets'][0]['outcomes'].append({'name': 'Draw', 'price': 300})
        self.assertTrue(audit(self.fixture)['market_checks'][0]['market_complete'])

    def test_http_and_fixture_boundary_errors(self):
        for fixture, status in [(self.fixture, 403), (self.fixture, 429), ({'events': []}, 200), ({'synthetic': True, 'events': {}}, 200)]:
            with self.subTest(status=status, fixture=fixture):
                with self.assertRaises(ValueError):
                    audit(fixture, status)

    def test_invalid_event_identity_is_rejected(self):
        self.fixture['events'][0]['id'] = ''
        with self.assertRaises(ValueError):
            audit(self.fixture)

    def test_four_builtin_nodes_and_one_note(self):
        self.assertEqual(set(NODES), {'APIRequest', 'DataOperations', 'ParserComponent', 'ChatOutput'})
        self.assertEqual(len(FLOW['data']['nodes']), 5)
        self.assertEqual(len(FLOW['data']['edges']), 3)
        for node in NODES.values():
            self.assertFalse(node['data']['node'].get('tool_mode', False))

    def test_request_is_one_public_get_without_credentials(self):
        fields = NODES['APIRequest']['data']['node']['template']
        self.assertEqual(fields['method']['value'], 'GET')
        self.assertEqual(fields['headers']['value'], [{'key': 'Accept', 'value': 'application/json'}])
        self.assertEqual(fields['body']['value'], [])
        self.assertEqual(fields['timeout']['value'], 30)
        self.assertFalse(fields['follow_redirects']['value'])
        self.assertFalse(fields['save_to_file']['value'])
        self.assertTrue(fields['url_input']['value'].startswith('https://raw.githubusercontent.com/JacobiusMakes/parlay-api-python/'))
        self.assertFalse(NODES['ChatOutput']['data']['node']['template']['should_store_message']['value'])

    def test_query_and_note_have_no_dash_or_live_data_claim(self):
        note = next(node['data']['node']['description'] for node in FLOW['data']['nodes'] if node['type'] == 'noteNode')
        self.assertNotRegex(QUERY + note + FLOW['description'], '[\u2013\u2014]')
        self.assertIn('fictional', note)
        self.assertIn('No current odds', note)
        self.assertIn('data redistribution rights', note)


if __name__ == '__main__':
    unittest.main()
