import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from grammar_core import AIClient, MAX_CHARS, SettingsStore, UsageStore, request_limit, apply_rules, check_rules, endpoint


class Response:
    def __init__(self, data):
        self.data = data
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, *_):
        return json.dumps(self.data).encode()


def reply(content=None, reason='stop'):
    return {'choices': [{'finish_reason': reason, 'message': {'content': content or
        '{"corrected":"I agree.","notes":["agree 是动词。"]}'}}],
        'usage': {'prompt_tokens': 120, 'completion_tokens': 25, 'total_tokens': 145}}


class ModelListTests(unittest.TestCase):
    def test_list_request(self):
        from grammar_core import fetch_models, _NoRedirect
        with patch('urllib.request.build_opener') as build:
            build.return_value.open.return_value = Response({'data': [{'id': 'b'}, {'id': 'a'}, {'id': 'a'}, {'id': 4}]})
            self.assertEqual(fetch_models('https://example.com/v1/chat/completions', 'test-key'), ['a', 'b'])
            request = build.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, 'https://example.com/v1/models')
            self.assertEqual(request.get_method(), 'GET')
            self.assertIsNone(request.data)
            self.assertIsInstance(build.call_args.args[0], _NoRedirect)

    def test_errors_and_validation(self):
        from grammar_core import fetch_models
        import urllib.error
        for base, key in [('http://example.com', 'key'), ('https://example.com', '')]:
            with self.assertRaises(ValueError):
                fetch_models(base, key)
        with patch('urllib.request.build_opener') as build:
            for data in ({'data': []}, {'unexpected': []}, []):
                build.return_value.open.return_value = Response(data)
                with self.assertRaises(ValueError):
                    fetch_models('https://example.com/v1', 'key')
            build.return_value.open.side_effect = urllib.error.HTTPError('https://example.com', 401, 'secret-body', {}, None)
            with self.assertRaisesRegex(ValueError, 'HTTP 401') as context:
                fetch_models('https://example.com/v1', 'key')
            self.assertNotIn('secret-body', str(context.exception))


class CoreTests(unittest.TestCase):
    def test_rules_and_overlap(self):
        text = 'I am agree. i  like like apples .'
        result = apply_rules(text, check_rules(text))
        self.assertEqual(result, 'I agree. I like apples.')
    def test_valid_sentence(self):
        self.assertEqual(check_rules('I agree with you.'), [])
    def test_context_not_claimed(self):
        self.assertEqual(check_rules('She have some question.'), [])
    def test_offsets(self):
        text = 'Hello\ni like tea.'
        issue = check_rules(text)[0]
        self.assertEqual(text[issue.start:issue.end], 'i')
    def test_endpoint(self):
        self.assertEqual(endpoint('https://api.deepseek.com/v1/'), 'https://api.deepseek.com/v1/chat/completions')
        self.assertEqual(endpoint('https://example.com/v1/chat/completions'), 'https://example.com/v1/chat/completions')
        for value in ['http://example.com', 'https://key@example.com', 'https://example.com?a=1']:
            with self.assertRaises(ValueError):
                endpoint(value)
    def settings(self):
        return {'base_url': 'https://example.com/v1', 'model': 'deepseek-chat', 'api_key': 'test-secret'}
    def test_api_and_cache(self):
        client = AIClient()
        with patch('urllib.request.OpenerDirector.open', return_value=Response(reply())) as mock:
            first = client.check('I am agree.', self.settings())
            second = client.check('I am agree.', self.settings())
            self.assertFalse(first['cached'])
            self.assertTrue(second['cached'])
            self.assertEqual(mock.call_count, 1)
            request = mock.call_args.args[0]
            body = json.loads(request.data)
            self.assertEqual(body['messages'][1]['content'], 'I am agree.')
            self.assertEqual(body['max_tokens'], 800)
            self.assertEqual(first['usage']['total_tokens'], 145)
            client.check('I am agree.', self.settings(), 'polish')
            self.assertEqual(mock.call_count, 2)
    def test_thinking_disabled_only_for_official_deepseek(self):
        for base in ['https://api.deepseek.com', 'https://api.deepseek.com/v1',
                     'https://api.openai.com/v1', 'https://example.com/v1',
                     'https://api.deepseek.com.example.com/v1']:
            with self.subTest(base=base), patch('urllib.request.OpenerDirector.open', return_value=Response(reply())) as mock:
                AIClient().check('Hello', {**self.settings(), 'base_url': base})
                body = json.loads(mock.call_args.args[0].data)
                if base in ['https://api.deepseek.com', 'https://api.deepseek.com/v1']:
                    self.assertEqual(body['thinking'], {'type': 'disabled'})
                else:
                    self.assertNotIn('thinking', body)

    def test_expression_tip_single_request(self):
        payload = json.dumps({'corrected': 'I agree.', 'notes': [], 'expression_tip': '可选：a few questions 更自然。'})
        with patch('urllib.request.OpenerDirector.open', return_value=Response(reply(payload))) as mock:
            result = AIClient().check('I agree.', self.settings())
            self.assertEqual(result['corrected'], 'I agree.')
            self.assertIn('a few', result['expression_tip'])
            self.assertEqual(mock.call_count, 1)
            body = json.loads(mock.call_args.args[0].data)
            self.assertIn('at most ONE', body['messages'][0]['content'])
        with patch('urllib.request.OpenerDirector.open', return_value=Response(reply())):
            self.assertEqual(AIClient().check('hello', self.settings())['expression_tip'], '')

    def test_chinese_translation_and_preserve_cache(self):
        from grammar_core import contains_chinese
        self.assertTrue(contains_chinese('明天 I will go.'))
        self.assertTrue(contains_chinese('中文'))
        self.assertTrue(contains_chinese('\U00020000'))
        self.assertFalse(contains_chinese('Hello！'))
        payload = json.dumps({'corrected': 'I will attend the meeting tomorrow.', 'notes': ['中文转英文。']})
        client = AIClient()
        for mode in ('grammar', 'polish'):
            with patch('urllib.request.OpenerDirector.open', return_value=Response(reply(payload))) as mock:
                result = client.check('明天 I will attend the meeting.', self.settings(), mode)
                self.assertTrue(result['translated'])
                prompt = json.loads(mock.call_args.args[0].data)['messages'][0]['content']
                self.assertIn('Translate the ENTIRE input', prompt)
                self.assertEqual(mock.call_count, 1)
        with patch('urllib.request.OpenerDirector.open', return_value=Response(reply(payload))) as mock:
            result = client.check('明天 I will attend the meeting.', {**self.settings(), 'chinese_mode': 'preserve'})
            self.assertFalse(result['translated'])
            self.assertFalse(result['cached'])
            self.assertIn('Preserve all Chinese text exactly', json.loads(mock.call_args.args[0].data)['messages'][0]['content'])
        with patch('urllib.request.OpenerDirector.open', return_value=Response(reply(payload))) as mock:
            result = AIClient().check('I agree.', self.settings())
            self.assertFalse(result['translated'])
            self.assertNotIn('Translate the ENTIRE input', json.loads(mock.call_args.args[0].data)['messages'][0]['content'])

    def test_incomplete_translation_no_retry_usage_counted(self):
        payload = json.dumps({'corrected': '明天 I agree.', 'notes': []})
        with tempfile.TemporaryDirectory() as directory:
            store = UsageStore(Path(directory) / 'usage.json')
            with patch('urllib.request.OpenerDirector.open', return_value=Response(reply(payload))) as mock:
                with self.assertRaisesRegex(ValueError, '仍含中文'):
                    AIClient(store).check('明天 I agree.', self.settings())
                self.assertEqual(mock.call_count, 1)
                self.assertEqual(store.summary()[1]['total'], 145)

    def test_bad_response_no_retry(self):
        with patch('urllib.request.OpenerDirector.open', return_value=Response(reply('not JSON'))) as mock:
            with self.assertRaisesRegex(ValueError, 'JSON'):
                AIClient().check('Hello', self.settings())
            self.assertEqual(mock.call_count, 1)
    def test_truncation(self):
        with patch('urllib.request.OpenerDirector.open', return_value=Response(reply(reason='length'))):
            with self.assertRaisesRegex(ValueError, '800'):
                AIClient().check('Hello', self.settings())
    def test_limits_and_key(self):
        client = AIClient()
        for text in ['', 'x' * (MAX_CHARS + 1)]:
            with self.assertRaises(ValueError):
                client.check(text, self.settings())
        client.calls = 1000
        with self.assertRaisesRegex(ValueError, '1000'):
            client.check('hello', self.settings())
        with self.assertRaises(ValueError):
            AIClient().check('hi', {**self.settings(), 'api_key': ''})
    def test_configurable_limit(self):
        client = AIClient()
        client.calls = 3
        with self.assertRaisesRegex(ValueError, '3'):
            client.check('hello', {**self.settings(), 'request_limit': 3})
        with patch('urllib.request.OpenerDirector.open', return_value=Response(reply())):
            client.check('hello', {**self.settings(), 'request_limit': 4})
        self.assertEqual(client.calls, 4)
        for invalid in [0, -1, '1.5', True, 100001, 'abc']:
            with self.assertRaises(ValueError):
                request_limit(invalid)

    def test_monthly_persistence_rollover_and_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'usage.json'
            now = [datetime(2026, 1, 31)]
            store = UsageStore(path, lambda: now[0])
            client = AIClient(store)
            with patch('urllib.request.OpenerDirector.open', return_value=Response(reply())):
                client.check('hello', self.settings())
                client.check('hello', self.settings())
            month, row, error = UsageStore(path, lambda: now[0]).summary()
            self.assertEqual(month, '2026-01')
            self.assertEqual(row['requests'], 1)
            self.assertEqual(row['total'], 145)
            self.assertIsNone(error)
            self.assertNotIn('test-secret', path.read_text())
            self.assertNotIn('hello', path.read_text())
            now[0] = datetime(2026, 2, 1)
            self.assertEqual(store.summary()[1]['total'], 0)
            store.record({'prompt_tokens': 4, 'completion_tokens': 5})
            self.assertEqual(store.summary()[1]['total'], 9)
            self.assertEqual(json.loads(path.read_text())['2026-01']['total'], 145)

    def test_invalid_content_usage_still_counted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = UsageStore(Path(directory) / 'usage.json')
            with patch('urllib.request.OpenerDirector.open', return_value=Response(reply('invalid'))):
                with self.assertRaises(ValueError):
                    AIClient(store).check('hello', self.settings())
            self.assertEqual(store.summary()[1]['total'], 145)

    def test_missing_usage_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'usage.json'
            store = UsageStore(path)
            store.record(None)
            self.assertEqual(store.summary()[1]['unreported'], 1)
            store.record({'prompt_tokens': -1, 'completion_tokens': True})
            self.assertEqual(store.summary()[1]['unreported'], 2)
            path.write_text('broken')
            store.record({'prompt_tokens': 1, 'completion_tokens': 2})
            self.assertIsNotNone(store.summary()[2])
            self.assertEqual(path.read_text(), 'broken')

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI')
    def test_secure_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            store = SettingsStore(path)
            settings = self.settings()
            store.save(settings)
            self.assertNotIn('test-secret', path.read_text())
            self.assertEqual(store.load()['api_key'], 'test-secret')


if __name__ == '__main__':
    unittest.main()
