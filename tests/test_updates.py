import io,json,unittest
from unittest.mock import Mock
from timesheet.updates import check,PREFIX,version


class UpdateTests(unittest.TestCase):
    def test_selects_complete_newer_release_and_validates_source_link(self):
        item=dict(tag_name='v0.5.0-rc1',html_url=PREFIX+'v0.5.0-rc1',draft=False,assets=[{'name':n} for n in ['TimeSheetLinux-x86_64.AppImage','TimeSheetLinux-x86_64.flatpak','SHA256SUMS','provenance.sigstore.json']])
        opener=Mock();opener.open.return_value=io.BytesIO(json.dumps([item]).encode())
        result=check('0.4.0-rc2',opener)
        self.assertTrue(result['newer']);self.assertTrue(result['provenance']);self.assertEqual(result['url'],item['html_url'])
        sent=opener.open.call_args.args[0];self.assertNotIn('Authorization',dict(sent.headers))
    def test_external_url_or_oversized_metadata_rejected(self):
        for body in [b'x'*524289,json.dumps([dict(tag_name='v9.0.0',html_url='https://other.test',assets=[])]).encode()]:
            opener=Mock();opener.open.return_value=io.BytesIO(body)
            with self.assertRaises(ValueError):check('0.4.0',opener)
    def test_stable_and_candidate_order(self):
        self.assertGreater(version('0.5.0'),version('0.5.0-rc99'))
        for bad in ['0.5','0.5.0; do something','x'*90]:
            with self.assertRaises(ValueError):version(bad)
    def test_malformed_asset_name_does_not_hide_a_valid_release(self):
        names=['TimeSheetLinux-x86_64.AppImage','TimeSheetLinux-x86_64.flatpak','SHA256SUMS']
        item=dict(tag_name='v0.6.1-rc2',html_url=PREFIX+'v0.6.1-rc2',assets=[{'name':{}}]+[{'name':n} for n in names])
        opener=Mock();opener.open.return_value=io.BytesIO(json.dumps([item]).encode())
        self.assertTrue(check('0.5.0',opener)['newer'])
