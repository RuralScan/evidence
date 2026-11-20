"""Prefilled/attached reviews feed the existing authenticated consensus path."""
import hashlib
import json
import unittest
from unittest.mock import patch, MagicMock

import attachments
import intake
import registers

PIN = 'a' * 40
URL = 'https://github.com/user-attachments/files/123/reviews.csv'
CSV = 'evidence_id,reviewer,decision,reason,note\ntest_bench_terrace,reader_a,hold,,Which page?\n'


def body(payload=CSV, inline=False, **changes):
    data = payload.encode()
    meta = dict(kind='csv', lane='T4', revision=PIN, test=True,
                sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), count=1)
    if inline:
        meta['payload'] = payload
    meta.update(changes)
    return attachments.HEADER + '\n\nReview decisions\n<!-- ruralscan-review\n' + json.dumps(meta) + '\n-->\n' + ('' if inline else '[reviews.csv](' + URL + ')')


def issue(text):
    return dict(number=123, node_id='123', user={'login':'reader_a'}, body=text,
                author_association='MEMBER', labels=[])


class AttachmentTests(unittest.TestCase):
    def test_inline_attachment_and_legacy_have_identical_votes(self):
        legacy = intake.decode(issue(intake.encode('csv','T4',PIN,CSV,test=True)))
        with patch('intake.original', return_value='reader_a') as original, patch('attachments.download', return_value=CSV.encode()) as get:
            self.assertEqual(intake.decode(issue(body(inline=True))), legacy)
            get.assert_not_called()
            self.assertEqual(intake.decode(issue(body())), legacy)
            get.assert_called_once_with(URL, len(CSV.encode()))
            self.assertEqual(original.call_count, 2)
        cohort = type('C', (), {'lanes': {}, 'reasons': {'other'}})()
        votes = intake.vote_rows(legacy, 'reader_a', cohort)
        self.assertEqual(votes[0]['decision'], 'hold')
        with self.assertRaisesRegex(ValueError, 'signed-in'):
            intake.vote_rows(legacy, 'impostor', cohort)

    def test_missing_changed_extra_and_oversized_files_rejected(self):
        with patch('attachments.download', return_value=b'wrong'):
            with self.assertRaisesRegex(ValueError, 'differs'):
                attachments.decode(body(), intake.unique_object)
        for text in [body().replace('[reviews.csv]('+URL+')',''), body()+'\n[second.csv]('+URL+')',
                     body(bytes=attachments.MAX_BYTES+1), body(inline=True, count=2),
                     body().replace(URL,'http://127.0.0.1/reviews.csv')]:
            with patch('attachments.download') as get, self.assertRaises(ValueError):
                attachments.decode(text, intake.unique_object)
            get.assert_not_called()

    def test_edited_receipt_rejected_before_download(self):
        with patch('intake.original', side_effect=ValueError('Edited')), patch('attachments.download') as get:
            with self.assertRaisesRegex(ValueError, 'Edited'):
                intake.decode(issue(body()))
            get.assert_not_called()

    def test_unavailable_opposing_attachment_aborts_instead_of_disappearing(self):
        with patch('intake.original', return_value='reader_a'), patch('attachments.download', side_effect=attachments.AttachmentUnavailable('Unavailable')):
            with self.assertRaises(attachments.AttachmentUnavailable):
                registers.authenticated([issue(body(test=False))])

    def test_unconfirmed_public_attachment_cannot_block_team_receipts(self):
        item = issue(body(test=False))
        item['author_association'] = 'NONE'
        with patch('attachments.download') as get:
            self.assertEqual(registers.authenticated([item]), {})
            get.assert_not_called()

    def test_scan_finds_old_and_new_receipts(self):
        old=issue(intake.encode('csv','T4',PIN,CSV,test=True))
        new=issue(body())
        with patch('intake.check_destination'), patch('intake.gh', return_value=[old,new,{'body':'unrelated'}]):
            self.assertEqual(intake.submissions(),[old,new])

    def test_redirect_cannot_reach_arbitrary_host_and_body_is_bounded(self):
        session=MagicMock(); response=session.get.return_value.__enter__.return_value
        response.is_redirect=True; response.headers={'Location':'http://127.0.0.1/internal'}
        with patch('attachments.requests.Session') as create:
            create.return_value.__enter__.return_value=session
            with self.assertRaisesRegex(ValueError,'address'):
                attachments.download(URL, 100)
            self.assertEqual(session.get.call_count,1)
        session.reset_mock(); response.is_redirect=False; response.headers={}; response.iter_content.return_value=[b'x'*101]
        with patch('attachments.requests.Session') as create:
            create.return_value.__enter__.return_value=session
            with self.assertRaisesRegex(ValueError,'size'):
                attachments.download(URL,100)

    def test_windows_csv_and_utf8_are_hashed_as_uploaded(self):
        payload=CSV.replace('Which page?', 'Which page — 水?').replace('\n','\r\n')
        with patch('attachments.download', return_value=payload.encode()):
            entry=attachments.decode(body(payload),intake.unique_object)
            self.assertEqual(entry['payload'],payload)
