import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from sentiment_claim_audit.core import audit, claims, evidence
from sentiment_claim_audit.phrases import SENTIMENT, NOSENTIMENT
from sentiment_claim_audit.__main__ import main


class Phrases(unittest.TestCase):
    def test_counts(self):
        self.assertEqual((len(SENTIMENT), len(NOSENTIMENT)), (60, 26))

    def test_normalization(self):
        self.assertEqual(claims("DOESN'T ANALYZE SENTIMENT"), ([], ['does not analyze sentiment']))
        self.assertEqual(claims('SENTIMENT-\nANALYSIS')[0], ['sentiment analysis'])

    def test_fences(self):
        for marker in ('```', '~~~', '   ````'):
            self.assertEqual(claims(marker+'\nsentiment analysis\n'+marker), ([], []))
        self.assertEqual(claims('`sentiment analysis`')[0], ['sentiment analysis'])

    def test_paragraphs_and_boundaries(self):
        self.assertEqual(claims('sentiment\n\nanalysis resentiment analysis sentiment analysiss'), ([], []))
        self.assertEqual(claims('positive negative neutral sentiment')[0], ['positive negative neutral sentiment'])


for index, phrase in enumerate(SENTIMENT):
    def test(self, phrase=phrase):
        self.assertEqual(claims(phrase), ([phrase], []))
    setattr(Phrases, 'test_positive_%02d' % index, test)
for index, phrase in enumerate(NOSENTIMENT):
    def test(self, phrase=phrase):
        self.assertEqual(claims(phrase), ([], [phrase]))
    setattr(Phrases, 'test_negative_%02d' % index, test)


GOOD = [
 'import transformers\ntransformers.pipeline("sentiment-analysis")',
 'import transformers as t\nt.pipeline(task="SENTIMENT_ANALYSIS_en")',
 'from transformers import pipeline as p\np("sentiment-analysis_en")',
 'from transformers import SentimentAnalysisPipeline as P\nP()',
 'import transformers\ntransformers.SentimentAnalysisPipeline()',
 'from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer as S\ns=S()\ns.polarity_scores("x")',
 'from nltk.sentiment import SentimentIntensityAnalyzer\nSentimentIntensityAnalyzer().polarity_scores("x")',
 'import nltk.sentiment.vader as v\na=v.SentimentIntensityAnalyzer()\na.polarity_scores("x")',
 'from textblob import TextBlob as B\nb=B("x")\nb.sentiment',
 'import textblob as t\nt.TextBlob("x").sentiment',
 'def f():\n from textblob import TextBlob\n return TextBlob("x").sentiment',
 'def f():\n from nltk.sentiment import SentimentIntensityAnalyzer as S\n return S().polarity_scores("x")',
]
for provider, constructor, operation in [('nltk.sentiment', 'SentimentIntensityAnalyzer', 'polarity_scores("x")'), ('textblob', 'TextBlob', 'sentiment')]:
    GOOD.append('from '+provider+' import '+constructor+' as C\nclass A:\n def run(self):\n  return self.obj.'+operation+'\n def __init__(self):\n  self.obj=C()')

BAD = [
 'words=["positive", "negative"]\nscore=sum(x in words for x in ["good"])',
 'import re\nre.findall(r":\\)", "x")',
 'client.chat.completions.create(model="generic")',
 'import subprocess\nsubprocess.run(["sentiment-analysis"])',
 'from transformers import pipeline',
 's="pipeline sentiment-analysis"',
 'from nltk.sentiment import SentimentIntensityAnalyzer as S\nS()',
 'from textblob import TextBlob\nTextBlob("x")',
 'from nltk.sentiment import SentimentIntensityAnalyzer as S\nS.polarity_scores("x")',
 'from textblob import TextBlob as B\nb=B("x")\nb=object()\nb.sentiment',
 'from nltk.sentiment import SentimentIntensityAnalyzer as S\ns=S()\ns=None\ns.polarity_scores("x")',
 'from textblob import TextBlob\ndef f(TextBlob):\n return TextBlob("x").sentiment',
 'from nltk.sentiment import SentimentIntensityAnalyzer as S\ndef f(S):\n return S().polarity_scores("x")',
 'def f():\n from textblob import TextBlob\nTextBlob("x").sentiment',
 'def f():\n from nltk.sentiment import SentimentIntensityAnalyzer as S\nS().polarity_scores("x")',
 'def f():\n from transformers import pipeline\npipeline("sentiment-analysis")',
 'from transformers import pipeline\ndef f(pipeline):\n pipeline("sentiment-analysis")',
 'from nltk.sentiment import SentimentIntensityAnalyzer as S\ns=S()\ndef f(s):\n return s.polarity_scores("x")',
 'from textblob import TextBlob as B\nb=B("x")\ndef f(b):\n return b.sentiment',
 'from transformers import pipeline\npipeline=None\npipeline("sentiment-analysis")',
 'from textblob import TextBlob\nclass TextBlob: pass\nTextBlob("x").sentiment',
 'not valid python !',
]
for task in ('text-classification', 'zero-shot-classification', 'emotion-classification', 'text-generation', 'resentiment-analysis', 'sentiment-analysiss'):
    BAD.append('from transformers import pipeline\npipeline('+repr(task)+')')
for name, suffix in [('pipeline', '("sentiment-analysis")'), ('SentimentAnalysisPipeline', '()'), ('SentimentIntensityAnalyzer', '().polarity_scores("x")'), ('TextBlob', '("x").sentiment')]:
    module = 'transformers' if name in ('pipeline', 'SentimentAnalysisPipeline') else 'textblob' if name == 'TextBlob' else 'nltk.sentiment'
    BAD.append('from '+module+' import '+name+'\ndef '+name+'(*args): pass\n'+name+suffix)

class Evidence(unittest.TestCase):
    pass
for label, cases, expected in [('good', GOOD, True), ('bad', BAD, False)]:
    for index, source in enumerate(cases):
        def test(self, source=source, expected=expected):
            self.assertEqual(evidence(source), expected, source)
        setattr(Evidence, 'test_%s_%02d' % (label, index), test)


class Integration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = main([str(self.root), *args])
        return code, output.getvalue()

    def test_no_source(self):
        self.put('README.md', 'sentiment analysis')
        self.assertEqual(self.cli()[0], 2)
        self.put('README.md', 'no sentiment analysis')
        self.assertEqual(self.cli(), (0, 'PASS\n'))

    def test_good_and_denial(self):
        self.put('README.md', 'sentiment analysis')
        self.put('app.py', GOOD[0])
        self.assertEqual(self.cli()[0], 0)
        self.put('README.md', 'no sentiment analysis')
        code, output = self.cli('--json')
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output)['findings'][0]['rule_id'], 'documented-no-sentiment-claim-false')

    def test_testonly(self):
        for name in ('tests/route.py', 'test_app.py', 'app_test.py'):
            with self.subTest(name=name):
                self.put('README.md', 'sentiment analysis')
                self.put(name, GOOD[0])
                self.assertEqual(self.cli()[0], 0)
                self.assertEqual(self.cli('--fail-on', 'MEDIUM')[0], 2)
                f = audit(self.root)['findings'][0]
                self.assertEqual((f['rule_id'], f['severity']), ('documented-sentiment-claim-false', 'MEDIUM'))
                (self.root/name).unlink()

    def test_scope(self):
        self.put('other.md', 'sentiment analysis')
        self.put('nested/README.md', 'sentiment analysis')
        self.assertEqual(self.cli()[0], 0)
        self.put('nested/docs/sub/a.md', 'sentiment analysis')
        for name in ('docs/a.py', 'examples/a.py', 'fixtures/a.py'):
            self.put(name, GOOD[0])
        self.assertEqual(self.cli()[0], 2)
        self.assertEqual(self.cli('--ignore', 'nested')[0], 0)

    def test_symlinks(self):
        self.put('README.md', 'sentiment analysis')
        self.put('fixtures/a.py', GOOD[0])
        (self.root/'app.py').symlink_to(self.root/'fixtures/a.py')
        (self.root/'linked').symlink_to(self.root/'fixtures', target_is_directory=True)
        self.assertEqual(self.cli()[0], 2)

    def test_options(self):
        self.put('README.md', 'sentiment analysis')
        self.put('src/a.py', GOOD[0])
        self.assertIn('src/a.py', self.cli('--verbose')[1])
        self.assertEqual(self.cli('--ignore', 'src')[0], 2)
        self.assertEqual(self.cli('--ignore', 'sr')[0], 0)
        self.assertEqual(self.cli('--version'), (0, '0.1.0\n'))
        self.assertEqual(self.cli('--unknown')[0], 1)
        self.assertEqual(self.cli('--fail-on', 'invalid')[0], 1)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['/nonexistent/audit-root']), 1)

    def test_self(self):
        self.assertEqual(audit(Path(__file__).resolve().parents[1])['status'], 'PASS')
