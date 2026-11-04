import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import monitor


def rows(asset='*.example.com', bounty=False):
    return [{'name': 'Example', 'url': 'https://hackerone.com/example',
             'targets': {'in_scope': [{'asset_type': 'WILDCARD',
                          'asset_identifier': asset, 'eligible_for_bounty': bounty,
                          'eligible_for_submission': True}]}}]


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.state = {'version': 1, 'platforms': {}, 'pending': []}
        self.current = monitor.normalize('hackerone', rows())

    def baseline(self):
        monitor.update(self.state, 'hackerone', self.current)
        self.state['pending'].clear()

    def test_baseline_has_only_confirmation_and_no_scope_flood(self):
        monitor.update(self.state, 'hackerone', self.current)
        self.assertEqual(len(self.state['pending']), 1)
        self.assertIn('baseline saved', self.state['pending'][0])
        self.assertNotIn('*.example.com', self.state['pending'][0])

    def test_unchanged_data_is_silent(self):
        self.baseline()
        monitor.update(self.state, 'hackerone', self.current)
        self.assertEqual(self.state['pending'], [])

    def test_new_scope_then_repeat(self):
        self.baseline()
        new = monitor.normalize('hackerone', rows('api.example.com'))
        monitor.update(self.state, 'hackerone', new)
        self.assertEqual(len(self.state['pending']), 1)
        self.assertIn('api.example.com', self.state['pending'][0])
        self.state['pending'].clear()
        monitor.update(self.state, 'hackerone', new)
        self.assertEqual(self.state['pending'], [])

    def test_feed_omission_does_not_cause_fake_relaunch(self):
        self.baseline()
        monitor.update(self.state, 'hackerone', {})
        monitor.update(self.state, 'hackerone', self.current)
        self.assertEqual(self.state['pending'], [])

    def test_new_program(self):
        self.baseline()
        new = rows()
        new[0]['url'] = 'https://hackerone.com/another'
        monitor.update(self.state, 'hackerone', monitor.normalize('hackerone', new))
        self.assertIn('NEW PROGRAM', self.state['pending'][0])

    def test_bounty_eligibility_transition(self):
        self.baseline()
        monitor.update(self.state, 'hackerone', monitor.normalize('hackerone', rows(bounty=True)))
        self.assertIn('Now bounty eligible', self.state['pending'][0])

    def test_bugcrowd_and_redacted_assets(self):
        data = [{'url': 'https://bugcrowd.com/engagements/example', 'name': 'Example',
                 'targets': {'in_scope': [{'type': 'website', 'target': '*.example.com'},
                                          {'type': 'website', 'target': '\u2588\u2588\u2588'}]}}]
        result = monitor.normalize('bugcrowd', data)
        self.assertEqual(len(next(iter(result.values()))['assets']), 1)

    def test_unsubmittable_assets_are_excluded(self):
        data = rows()
        data[0]['targets']['in_scope'][0]['eligible_for_submission'] = False
        result = monitor.normalize('hackerone', data)
        self.assertEqual(next(iter(result.values()))['assets'], {})

    def test_malformed_feed_rejected(self):
        for data in ([], {}, [{'name': 'Oops'}]):
            with self.subTest(data=data), self.assertRaises(monitor.MonitorError):
                monitor.normalize('hackerone', data)

    def test_chunk_size_with_emoji_and_long_lines(self):
        for text in ('x' * 11000, '\U0001f514' * 7000, ('a' * 500 + '\n') * 30):
            result = list(monitor.chunks(text))
            self.assertTrue(result)
            self.assertTrue(all(len(part.encode('utf-16-le')) // 2 <= 4096 for part in result))

    def test_delivery_progress_survives_failure(self):
        self.state['pending'] = ['one', 'two', 'three']
        delivered = []
        def sender(token, chat_id, message):
            if message == 'two':
                raise monitor.MonitorError('offline')
            delivered.append(message)
        with tempfile.TemporaryDirectory() as directory, patch('monitor.time.sleep'):
            path = Path(directory) / 'state.json'
            monitor.save(path, self.state)
            with self.assertRaises(monitor.MonitorError):
                monitor.deliver(self.state, path, 'dummy', 'dummy', sender)
            persisted = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(delivered, ['one'])
            self.assertEqual(persisted['pending'], ['two', 'three'])

    def test_invalid_feed_does_not_modify_state(self):
        self.baseline()
        previous = copy.deepcopy(self.state)
        with self.assertRaises(monitor.MonitorError):
            monitor.normalize('hackerone', [{'url': 'https://evil.example/', 'name': 'X'}])
        self.assertEqual(previous, self.state)


if __name__ == '__main__':
    unittest.main()
