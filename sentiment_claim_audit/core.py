"""Offline documentation and Python AST inspection."""
import ast
import re
from pathlib import Path
from .phrases import SENTIMENT, NOSENTIMENT


def normalize(text):
    return ' '.join(text.lower().replace("n't", ' not').replace('-', ' ').split())


def pattern(phrases):
    return re.compile(r'\b(?:' + '|'.join(re.escape(p) for p in sorted(phrases, key=lambda p: (-len(p), p))) + r')\b')


YES, NO = pattern(SENTIMENT), pattern(NOSENTIMENT)


def claims(text):
    lines, fence = [], None
    for line in text.splitlines():
        match = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                fence = None
            lines.append('')
        elif match:
            fence = match[1]
            lines.append('')
        else:
            lines.append(line)
    positive, negative = [], []
    for paragraph in re.split(r'\n\s*\n', '\n'.join(lines)):
        text = normalize(paragraph)
        negative.extend(m.group() for m in NO.finditer(text))
        text = NO.sub(' ', text)
        positive.extend(m.group() for m in YES.finditer(text))
    return positive, negative


def evidence(source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    found = False
    def block(nodes, inherited, attrs=None):
        nonlocal found
        env = dict(inherited)
        attrs = {} if attrs is None else attrs
        # Python local declarations shadow outer bindings throughout a scope.
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                env[node.name] = None
        def resolve(n):
            if isinstance(n, ast.Name):
                return env.get(n.id)
            if isinstance(n, ast.Attribute):
                if isinstance(n.value, ast.Name) and n.value.id == 'self':
                    return attrs.get(n.attr)
                parent = resolve(n.value)
                return parent + '.' + n.attr if parent and not parent.startswith('@') else None
            if isinstance(n, ast.Call):
                name = resolve(n.func)
                if name in constructors:
                    return '@' + constructors[name]
            return None
        def expr(n):
            nonlocal found
            for child in ast.iter_child_nodes(n):
                expr(child)
            if isinstance(n, ast.Call):
                name = resolve(n.func)
                if name in pipelines:
                    values = list(n.args[:1]) + [k.value for k in n.keywords if k.arg == 'task']
                    if any(isinstance(v, ast.Constant) and isinstance(v.value, str) and re.search(r'(?<![a-z])sentiment analysis(?![a-z])', normalize(v.value.replace('_', ' '))) for v in values):
                        found = True
                if name in sentiment_pipelines:
                    found = True
                if isinstance(n.func, ast.Attribute) and n.func.attr == 'polarity_scores' and resolve(n.func.value) == '@vader':
                    found = True
            if isinstance(n, ast.Attribute) and n.attr == 'sentiment' and resolve(n.value) == '@blob':
                found = True
        def bind(target, value):
            if isinstance(target, ast.Name):
                env[target.id] = value
            elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == 'self':
                attrs[target.attr] = value
            elif isinstance(target, (ast.Tuple, ast.List)):
                for t in target.elts:
                    bind(t, None)
        for n in nodes:
            if isinstance(n, ast.Import):
                for a in n.names:
                    env[a.asname or a.name.split('.')[0]] = a.name if a.asname else a.name.split('.')[0]
            elif isinstance(n, ast.ImportFrom):
                for a in n.names:
                    env[a.asname or a.name] = (n.module or '') + '.' + a.name if not n.level else None
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                env[n.name] = None
                inner = dict(env)
                for arg in n.args.posonlyargs + n.args.args + n.args.kwonlyargs + ([n.args.vararg] if n.args.vararg else []) + ([n.args.kwarg] if n.args.kwarg else []):
                    inner[arg.arg] = None
                # assignments establish local bindings even before execution
                for s in ast.walk(n):
                    if isinstance(s, ast.Name) and isinstance(s.ctx, ast.Store):
                        inner[s.id] = None
                block(n.body, inner, attrs)
            elif isinstance(n, ast.ClassDef):
                env[n.name] = None
                class_attrs = {}
                # Collect constructor attributes before inspecting other methods.
                ordered = sorted(n.body, key=lambda s: 0 if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)) and s.name == '__init__' else 1)
                block(ordered, env, class_attrs)
            elif isinstance(n, (ast.Assign, ast.AnnAssign)):
                if n.value:
                    expr(n.value)
                value = resolve(n.value) if n.value else None
                for t in n.targets if isinstance(n, ast.Assign) else [n.target]:
                    bind(t, value)
            elif isinstance(n, (ast.AugAssign, ast.Delete)):
                for t in n.targets if isinstance(n, ast.Delete) else [n.target]:
                    bind(t, None)
            elif isinstance(n, (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.AsyncFor, ast.AsyncWith)):
                for field, value in ast.iter_fields(n):
                    if isinstance(value, list) and value and isinstance(value[0], ast.stmt):
                        block(value, env, attrs)
                    elif isinstance(value, ast.expr):
                        expr(value)
            else:
                expr(n)
    block(tree.body, {})
    return found


pipelines = {'transformers.pipeline', 'transformers.pipelines.pipeline'}
sentiment_pipelines = {'transformers.SentimentAnalysisPipeline', 'transformers.pipelines.SentimentAnalysisPipeline', 'transformers.pipelines.text_classification.SentimentAnalysisPipeline'}
constructors = {name: 'vader' for name in ('vaderSentiment.vaderSentiment.SentimentIntensityAnalyzer', 'nltk.sentiment.SentimentIntensityAnalyzer', 'nltk.sentiment.vader.SentimentIntensityAnalyzer')}
constructors.update({'textblob.TextBlob': 'blob', 'textblob.blob.TextBlob': 'blob'})


def audit(root, ignores=()):
    root = Path(root)
    if not root.is_dir():
        raise OSError('root must be an existing directory')
    positive, negative, production, tests = [], [], [], []
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if any(p.is_symlink() for p in [path, *path.parents] if p != root.parent):
            continue
        if any(rel.as_posix() == i.rstrip('/') or rel.as_posix().startswith(i.rstrip('/') + '/') for i in ignores):
            continue
        if not path.is_file():
            continue
        if rel.as_posix() == 'README.md' or ('docs' in rel.parts and path.suffix == '.md'):
            yes, no = claims(path.read_text(encoding='utf-8'))
            positive.extend(yes)
            negative.extend(no)
        if path.suffix == '.py':
            if any(p in rel.parts for p in ('fixtures', 'docs', 'examples')):
                continue
            is_test = 'tests' in rel.parts or path.name.startswith('test_') or path.name.endswith('_test.py')
            if evidence(path.read_text(encoding='utf-8')):
                (tests if is_test else production).append(rel.as_posix())
    findings = []
    if positive and not production:
        findings.append({'rule_id': 'documented-sentiment-claim-false', 'severity': 'MEDIUM' if tests else 'HIGH', 'message': 'Documented claim has evidence only in tests.' if tests else 'Documented claim has no production evidence.'})
    if negative and production:
        findings.append({'rule_id': 'documented-no-sentiment-claim-false', 'severity': 'HIGH', 'message': 'Documented denial conflicts with production evidence.'})
    return {'status': 'FAIL' if findings else 'PASS', 'findings': findings, 'evidence': {'production': production, 'tests': tests}}
