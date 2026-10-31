"""Run from the repository using python3 tests/verify_distributions.py."""
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(args, code=0, cwd=None):
    result = subprocess.run([str(a) for a in args], cwd=cwd, text=True, capture_output=True)
    if result.returncode != code:
        raise AssertionError((args, result.returncode, result.stdout, result.stderr))
    return result.stdout


def main():
    artifacts = sorted((ROOT/'dist').glob('*.whl')) + sorted((ROOT/'dist').glob('*.tar.gz'))
    assert len(artifacts) == 2
    for artifact in artifacts:
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            env = temp/'venv'
            run(['python3', '-m', 'venv', env])
            interpreter = env/'bin/python3'
            run([interpreter, '-m', 'pip', 'install', '--no-deps', artifact], cwd=temp)
            cases = {
                'good': ('sentiment analysis', 'app.py'),
                'bad': ('sentiment analysis', None),
                'testonly': ('sentiment analysis', 'tests/test_app.py'),
                'no': ('no sentiment analysis', 'app.py'),
            }
            for name, (doc, source) in cases.items():
                path = temp/name
                path.mkdir()
                (path/'README.md').write_text(doc)
                if source:
                    file = path/source
                    file.parent.mkdir(exist_ok=True)
                    file.write_text('from transformers import pipeline\npipeline("sentiment-analysis")\n')
            for entry in ([env/'bin/sentiment-claim-audit'], [interpreter, '-m', 'sentiment_claim_audit']):
                assert run(entry + ['--version'], cwd=temp).strip() == '0.1.0'
                for case, code, rule, severity in [
                    ('good', 0, None, None),
                    ('bad', 2, 'documented-sentiment-claim-false', 'HIGH'),
                    ('testonly', 0, 'documented-sentiment-claim-false', 'MEDIUM'),
                    ('no', 2, 'documented-no-sentiment-claim-false', 'HIGH'),
                ]:
                    output = json.loads(run(entry + [temp/case, '--json'], code, cwd=temp))
                    assert [(f['rule_id'], f['severity']) for f in output['findings']] == ([(rule, severity)] if rule else [])
                run(entry + [temp/'testonly', '--fail-on', 'MEDIUM'], 2, cwd=temp)
                assert json.loads(run(entry + [ROOT, '--json'], cwd=temp))['status'] == 'PASS'
            print(artifact.name + ': fresh-venv install and all smoke checks PASS')


if __name__ == '__main__':
    main()
