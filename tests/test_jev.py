import io
import json
import traceback
import unittest
import urllib.error
from unittest.mock import Mock, patch
from timesheet import jev


class Response:
    def __init__(self, value):
        self.value = json.dumps(value).encode()
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def read(self, _): return self.value


def answer(choice='task_7', probabilities=None, **extra):
    return {'answers': {'task': {'type': 'choice', 'choice': choice,
            'probabilities': probabilities or {'task_7': 0.87, 'none': 0.13}}}, **extra}


def opener_for(value):
    opener = Mock()
    opener.open.return_value = Response(value)
    return opener


class JevTests(unittest.TestCase):
    def test_explicit_choice_sends_only_expected_data(self):
        opener = opener_for(answer())
        task, probability = jev.suggest(['Editor'], [(7, 'Client / Project / Design')], 'private-key', opener)
        self.assertEqual((task, probability), (7, 0.87))
        request = opener.open.call_args.args[0]
        data = json.loads(request.data)
        self.assertEqual(request.full_url, 'https://api.typesafe.ai/v1/systemone')
        self.assertEqual(data['state'], {'applications': ['Editor']})
        self.assertEqual(data['questions']['task']['criteria']['task_7'], 'Client / Project / Design')
        self.assertIn('none', data['questions']['task']['criteria'])
        self.assertNotIn('private-key', request.data.decode())
        self.assertEqual(request.get_header('Authorization'), 'Bearer private-key')
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 15)

    def test_explicit_connection_check_only_sends_key_to_official_models_endpoint(self):
        opener = opener_for({'models': [{'name': 'jev-latest'}, {'name': 'jev-1.14.0'}, {'name': 'jev-latest'}]})
        names = jev.check_connection('private-key', opener)
        self.assertEqual(names, ['jev-latest', 'jev-1.14.0'])
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.typesafe.ai/v1/models')
        self.assertEqual(request.method, 'GET'); self.assertIsNone(request.data)
        self.assertEqual(request.get_header('Authorization'), 'Bearer private-key')
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 15)
        self.assertEqual(jev.check_connection('k', opener_for({'models': []})), [])

    def test_connection_check_rejects_invalid_lists_and_keys(self):
        for value in (None, [], {'models': {}}, {'models': [None]}, {'models': [{'name': 'bad\nname'}]}, {'models': [{'name': 'bad name'}]}, {'models': [{'name': 4}]}):
            with self.subTest(value=value), self.assertRaises(jev.JevError):
                jev.check_connection('k', opener_for(value))
        opener = Mock()
        with self.assertRaises(jev.JevError): jev.check_connection('bad\rkey', opener)
        opener.open.assert_not_called()

    def test_connection_check_uses_safe_http_and_response_limits(self):
        opener = Mock()
        error = urllib.error.HTTPError(jev.MODELS_ENDPOINT, 302, 'private-key', {}, io.BytesIO(b'secret'))
        opener.open.side_effect = error
        with self.assertRaises(jev.JevError) as caught: jev.check_connection('private-key', opener)
        self.assertIn('redirect', str(caught.exception))
        self.assertNotIn('private-key', ''.join(traceback.format_exception(caught.exception)))
        response = Response({}); response.value = b' ' * (jev.MAX_RESPONSE + 1)
        opener = Mock(); opener.open.return_value = response
        with self.assertRaisesRegex(jev.JevError, 'oversized'): jev.check_connection('k', opener)

    def test_pure_request_preview_matches_outbound_payload_without_key_access(self):
        with patch.object(jev, '_secret', side_effect=AssertionError('key accessed')):
            payload = jev.prepare_request(['Editor', 'Browser'], [(7, 'Task')], context='Edited context')
        opener = opener_for(answer())
        jev.suggest(['Editor', 'Browser'], [(7, 'Task')], 'k', opener, context='Edited context')
        self.assertEqual(payload, json.loads(opener.open.call_args.args[0].data))
        self.assertNotIn('Authorization', str(payload))

    def test_optional_context_and_two_choices_remain_reviewable(self):
        response = answer(probabilities={'task_7': 0.46, 'task_8': 0.42, 'none': 0.12})
        response['answers']['personal'] = {'type': 'noul', 'noul': 0.8}
        opener = opener_for(response)
        result = jev.suggest(['Editor'], [(7, 'Design'), (8, 'Admin')], 'k', opener,
                             context='Edited context', detailed=True)
        self.assertEqual(result['alternatives'], [(7, 0.46), (8, 0.42)])
        self.assertEqual(result['personal'], 0.8)
        self.assertEqual(json.loads(opener.open.call_args.args[0].data)['state']['user_edited_context'], 'Edited context')
        with self.assertRaises(jev.JevError):
            jev.suggest(['Editor'], [(7, 'Task')], 'k', opener, context='x' * 1001)

    def test_none_is_a_valid_choice_and_missing_personal_is_unavailable(self):
        opener = opener_for(answer('none', {'none': 0.7, 'task_7': 0.3}))
        self.assertEqual(jev.suggest(['Editor'], [(7, 'Task')], 'k', opener), (None, 0.7))
        self.assertIsNone(jev.suggest(['Editor'], [(7, 'Task')], 'k', opener, detailed=True)['personal'])

    def test_detailed_metadata_uses_actual_reported_model_and_usage(self):
        opener = opener_for(answer(model='jev-1.14.0', usage={'input_tokens': 120, 'output_tokens': 12}))
        result = jev.suggest(['Editor'], [(7, 'Task')], 'k', opener, detailed=True)
        self.assertEqual(result['model'], 'jev-1.14.0')
        self.assertEqual(result['usage'], {'input_tokens': 120, 'output_tokens': 12})
        result = jev.suggest(['Editor'], [(7, 'Task')], 'k', opener_for(answer()), detailed=True)
        self.assertIsNone(result['model']); self.assertIsNone(result['usage'])

    def test_unrecognised_and_malformed_responses_are_rejected_in_both_modes(self):
        values = [None, [], {'answers': []}, {'answers': {'task': []}},
                  answer('task_99'), answer(choice=['task_7']),
                  answer(probabilities={'task_7': 2, 'none': -1}),
                  answer(probabilities={'task_7': 0.87}),
                  answer(probabilities={'task_7': 0.5, 'none': 0.1}),
                  answer(probabilities={'task_7': 0.3, 'none': 0.7}),
                  answer(probabilities={'task_7': True, 'none': 0}),
                  answer(probabilities={'task_7': float('nan'), 'none': 0.1}),
                  answer(probabilities={'task_7': 10**500, 'none': 0}),
                  answer(probabilities={'task_7': 0.8, 'unknown': 0.2})]
        bad_personal = answer(); bad_personal['answers']['personal'] = {'type': 'noul', 'noul': 'yes'}
        values.append(bad_personal)
        bad_confidence = answer(); bad_confidence['answers']['task']['confidence'] = False
        values.append(bad_confidence)
        for value in values:
            for detailed in (False, True):
                with self.subTest(value=value, detailed=detailed), self.assertRaises(jev.JevError):
                    jev.suggest(['Editor'], [(7, 'Task')], 'k', opener_for(value), detailed=detailed)

    def test_duplicate_json_keys_and_oversized_responses_are_rejected(self):
        response = Response({})
        response.value = b'{"answers":{},"answers":{"task":{}}}'
        opener = Mock(); opener.open.return_value = response
        with self.assertRaises(jev.JevError): jev.suggest(['Editor'], [(7, 'Task')], 'k', opener)
        response.value = b' ' * (jev.MAX_RESPONSE + 1)
        with self.assertRaisesRegex(jev.JevError, 'oversized'):
            jev.suggest(['Editor'], [(7, 'Task')], 'k', opener)

    def test_invalid_metadata_never_drives_usage_display(self):
        values = [answer(model=[]), answer(usage=[]), answer(usage={'input_tokens': True, 'output_tokens': 1}),
                  answer(usage={'input_tokens': -1, 'output_tokens': 0})]
        for value in values:
            with self.subTest(value=value), self.assertRaises(jev.JevError):
                jev.suggest(['Editor'], [(7, 'Task')], 'k', opener_for(value), detailed=True)

    def test_invalid_inputs_never_open_a_connection(self):
        opener = Mock()
        values = [(None, [(7, 'Task')], 'k'), (['Editor'], [(True, 'Task')], 'k'),
                  (['Editor'], [(7, None)], 'k'), (['Editor'], [(2**100, 'Task')], 'k'), (['Editor'], [(7, 'Task'), (7, 'Duplicate')], 'k'),
                  (['Editor\n'], [(7, 'Task')], 'k'), ([None], [(7, 'Task')], 'k'),
                  (['Editor'], [(7, 'Task')], 'bad\rkey'), (['Editor'], [(7, 'Task')], 'bad\x00key'),
                  (['Editor'], [(7, 'Task')], 'bad key'), (['Editor'], [(7, 'Task')], 'é'),
                  (['Editor'], [(n, str(n)) for n in range(1, 256)], 'k')]
        for apps, tasks, key in values:
            with self.subTest(apps=apps, tasks=tasks, key=key), self.assertRaises(jev.JevError):
                jev.suggest(apps, tasks, key, opener)
        opener.open.assert_not_called()

    def test_request_size_and_invalid_context_prevent_network_calls(self):
        opener = Mock()
        with self.assertRaises(jev.JevError):
            jev.suggest(['Editor'], [(i, 'x' * 300) for i in range(1, 150)], 'k', opener)
        for context in ('text\x00secret', '\ud800', 'x' * 1001):
            with self.assertRaises(jev.JevError): jev.suggest(['Editor'], [(7, 'Task')], 'k', opener, context=context)
        opener.open.assert_not_called()

    def test_http_errors_do_not_expose_response_key_or_chained_traceback(self):
        for code in (302, 401, 402, 403, 429, 529):
            opener = Mock()
            error = urllib.error.HTTPError(jev.ENDPOINT, code, 'private-key', {}, io.BytesIO(b'secret content'))
            opener.open.side_effect = error
            with self.assertRaises(jev.JevError) as caught:
                jev.suggest(['Editor'], [(7, 'Task')], 'private-key', opener)
            output = ''.join(traceback.format_exception(caught.exception))
            self.assertNotIn('private-key', output); self.assertNotIn('secret content', output)
            self.assertTrue(caught.exception.__suppress_context__)
            self.assertTrue(error.fp is None or error.fp.closed)

    def test_network_errors_are_safe_and_not_retried(self):
        opener = Mock(); opener.open.side_effect = urllib.error.URLError('private-key')
        with self.assertRaises(jev.JevError) as caught: jev.suggest(['Editor'], [(7, 'Task')], 'k', opener)
        self.assertNotIn('private-key', ''.join(traceback.format_exception(caught.exception)))
        self.assertEqual(opener.open.call_count, 1)

    def test_redirects_never_forward_credentials(self):
        self.assertIsNone(jev._NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example/'))

    def test_keyring_operations_use_secret_service(self):
        secret = Mock(); secret.COLLECTION_DEFAULT = 'default'; secret.password_store_sync.return_value = True
        secret.password_lookup_sync.return_value = 'user-key'
        with patch.object(jev, '_secret', return_value=(secret, 'schema')):
            jev.save_key(' user-key ')
            self.assertEqual(jev.get_key(), 'user-key')
            jev.delete_key()
        secret.password_store_sync.assert_called_once_with('schema', {'service': 'typesafe'}, 'default',
            'Time Sheet Linux — TypeSafe API key', 'user-key', None)
        secret.password_clear_sync.assert_called_once_with('schema', {'service': 'typesafe'}, None)

    def test_keyring_failures_do_not_expose_low_level_errors(self):
        secret = Mock(); secret.password_lookup_sync.side_effect = RuntimeError('private-key')
        with patch.object(jev, '_secret', return_value=(secret, 'schema')):
            with self.assertRaises(jev.JevError) as caught: jev.get_key()
        self.assertNotIn('private-key', ''.join(traceback.format_exception(caught.exception)))
        secret.password_lookup_sync.side_effect = None; secret.password_lookup_sync.return_value = 'bad\nkey'
        with patch.object(jev, '_secret', return_value=(secret, 'schema')):
            with self.assertRaises(jev.JevError): jev.get_key()

    def test_batch_is_bounded_and_cancellable(self):
        results, calls = [], []
        def request(apps, tasks, key): calls.append(apps[0]); return (7, 0.8)
        jev.suggest_batch(['A', 'B', 'C'], [(7, 'Task')], 'k', lambda: len(calls) >= 2,
                          lambda *value: results.append(value), request=request)
        self.assertEqual(calls, ['A', 'B']); self.assertEqual(results, [(0, (7, 0.8), None)])
        with self.assertRaises(jev.JevError):
            jev.suggest_batch(['A'] * 11, [(7, 'Task')], 'k', lambda: False, lambda *value: None, request=request)

    def test_whole_batch_is_validated_before_any_request(self):
        request = Mock()
        for apps in (['A', 'bad\nname'], ['A', None], 'A'):
            with self.assertRaises(jev.JevError):
                jev.suggest_batch(apps, [(7, 'Task')], 'k', lambda: False, lambda *value: None, request=request)
        request.assert_not_called()
        jev.suggest_batch(['A'], [(7, 'Task')], 'k', lambda: True, lambda *value: None, request=request)
        request.assert_not_called()

    def test_batch_stops_on_first_error_without_retry(self):
        for error, expected in ((jev.JevError('Unavailable'), 'Unavailable'), (RuntimeError('private-key'), 'The suggestion request failed.')):
            request = Mock(side_effect=error); results = []
            jev.suggest_batch(['A', 'B'], [(7, 'Task')], 'k', lambda: False,
                              lambda *value: results.append(value), request=request)
            self.assertEqual(request.call_count, 1); self.assertEqual(results, [(0, None, expected)])

    def test_missing_key_and_storage_errors_are_safe(self):
        with patch.object(jev, '_secret', side_effect=jev.JevError('Unavailable')):
            with self.assertRaises(jev.JevError): jev.get_key()
        for key in ('bad\nkey', None, 7):
            with self.assertRaises(jev.JevError): jev.save_key(key)


if __name__ == '__main__': unittest.main()
