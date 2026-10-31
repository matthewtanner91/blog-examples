#!/usr/bin/env python3
"""Run synthetic projects only; no install, trust modification, credentials, or upload."""
from pathlib import Path
import argparse, datetime, json, os, re, shutil, subprocess, sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'run-output'
NS = {'m': 'http://maven.apache.org/POM/4.0.0'}

def record(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')

def change_pom(path, remove=(), jupiter_only=False):
    # Preserve source formatting and change only the explicitly selected elements.
    text = path.read_text()
    for artifact in remove:
        pattern = r'    <dependency><groupId>[^<]+</groupId><artifactId>' + re.escape(artifact) + r'</artifactId>.*?</dependency>\n'
        text, count = re.subn(pattern, '', text)
        if count != 1:
            raise RuntimeError('Unexpected dependency layout: ' + artifact)
    if jupiter_only:
        original = '<artifactId>maven-surefire-plugin</artifactId><version>3.5.3</version>'
        addition = '<configuration><includeJUnit5Engines><engine>junit-jupiter</engine></includeJUnit5Engines></configuration>'
        if text.count(original) != 1:
            raise RuntimeError('Unexpected Surefire configuration')
        text = text.replace(original, original + addition)
    ET.fromstring(text)
    path.write_text(text)

def parse_reports(directory):
    rows = []
    for path in sorted(directory.glob('TEST-*.xml')):
        root = ET.parse(path).getroot()
        for case in root.iter('testcase'):
            name = case.get('name', '')
            classname = case.get('classname', '')
            # Surefire reporters may append parentheses after switching engines.
            normalized = name[:-2] if classname == 'example.LegacyTest' and name.endswith('()') else name
            status = 'passed'
            details = ''
            for kind in ('failure', 'error', 'skipped'):
                child = case.find(kind)
                if child is not None:
                    status = kind
                    details = ' '.join([child.get('message', ''), child.get('type', ''), ''.join(child.itertext())])
                    break
            rows.append({'identity': classname + '#' + normalized, 'raw_name': name, 'status': status, 'details': details, 'xml': path.name})
    if not rows:
        raise AssertionError('No XML test cases; a green process alone is insufficient')
    ids = [r['identity'] for r in rows]
    assert len(ids) == len(set(ids)), 'Duplicate reported identities'
    return sorted(rows, key=lambda r: r['identity'])

def contract(rows, mode):
    pairs = {r['identity']: r['status'] for r in rows}
    if mode == 'tag':
        assert pairs == {'example.LegacyTest#doublesQuantity': 'passed'}, pairs
    elif mode == 'control':
        assert len(rows) == 3 and all(r['identity'].startswith('example.ModernTest#') and r['status'] == 'passed' for r in rows), pairs
    else:
        assert len(rows) == 7, pairs
        assert sum(r['status'] == 'passed' for r in rows) == 5, pairs
        assert sum(r['status'] == 'skipped' for r in rows) == 2, pairs
        assert pairs['example.LegacyTest#doublesQuantity'] == 'passed'
        assert pairs['example.LegacyTest#rejectsNegativeQuantity'] == 'passed'
        for name, reason in [('disabledCase', 'intentional fixture skip'), ('absentEnvironment', 'no integration target')]:
            row = next(r for r in rows if r['identity'] == 'example.LegacyTest#' + name)
            assert row['status'] == 'skipped' and reason in row['details'], row
        assert sum(r['identity'].startswith('example.ModernTest#') for r in rows) == 3
    return pairs

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true', help='Perform bounded Maven runs; otherwise print plan only')
    args = parser.parse_args()
    if not args.run:
        print('Plan only. Read README.md, inspect existing java/mvn/python versions, then use --run when authorized.')
        return
    if OUT.exists():
        raise SystemExit('run-output already exists; refusing to overwrite evidence. Use a fresh extracted copy.')
    OUT.mkdir()
    versions = {}
    for name, command in [('java', ['java', '-version']), ('maven', ['mvn', '-version']), ('python', [sys.executable, '--version'])]:
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        versions[name] = {'command': command, 'returncode': result.returncode, 'output': result.stdout}
    record(OUT / 'versions.json', versions)
    assert versions['java']['returncode'] == versions['maven']['returncode'] == 0, 'Missing existing tools'
    assert re.search(r'version\s+"17\.', versions['java']['output']), 'Expected existing Java17; no installation attempted'
    assert 'Apache Maven 3.9.12' in versions['maven']['output'], 'Expected existing Maven3.9.12; no installation attempted'
    assert re.search(r'Java version:\s*17\.', versions['maven']['output']), 'Maven itself must use existing Java17'
    env = os.environ.copy()
    env['MAVEN_ARGS'] = '-Dmaven.repo.local=' + str(OUT / 'm2')
    results = []
    baseline = None
    stages = [
        ('01-mixed', False, (), False, False, False),
        ('02-ci-replay', False, (), False, False, True),
        ('03-mixed-tag', False, (), False, True, False),
        ('04-jupiter-only-control', False, (), True, False, False),
        ('05-converted', True, (), False, False, False),
        ('06-converted-tag', True, (), False, True, False),
        ('07-no-vintage', True, ('junit-vintage-engine',), False, False, False),
        ('08-no-junit4', True, ('junit-vintage-engine', 'junit'), False, False, False),
    ]
    for name, converted, remove, control, tag, ci in stages:
        stage = OUT / name
        project = stage / 'project'
        shutil.copytree(ROOT / 'baseline', project)
        if converted:
            shutil.copy2(ROOT / 'LegacyTest.converted.java', project / 'src/test/java/example/LegacyTest.java')
        change_pom(project / 'pom.xml', remove, control)
        command = ['sh', 'ci.sh'] if ci else ['mvn', '-B', '-ntp', 'clean', 'verify']
        if tag:
            command += ['-Dgroups=example.LegacyTest$Smoke']
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        result = subprocess.run(command, cwd=project, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (stage / 'maven.log').write_text(result.stdout)
        receipt = {'command': command, 'cwd': str(project), 'started': started, 'returncode': result.returncode, 'local_ci_replay_not_hosted': ci}
        record(stage / 'command.json', receipt)
        if result.returncode:
            raise RuntimeError(name + ' failed; stopped. Inspect saved log without disabling TLS or changing trust.')
        rows = parse_reports(project / 'target/surefire-reports')
        record(stage / 'test-cases.json', rows)
        pairs = contract(rows, 'control' if control else 'tag' if tag else 'full')
        if name == '01-mixed':
            baseline = pairs
        elif not control and not tag:
            assert pairs == baseline, 'Identity/outcome drift in ' + name
        results.append({'stage': name, 'cases': len(rows), 'passed': sum(r['status'] == 'passed' for r in rows), 'skipped_or_aborted': sum(r['status'] == 'skipped' for r in rows), 'contract_checked': True})
        record(OUT / 'results.json', results)
    record(OUT / 'completion.json', {'status': 'All eight synthetic checks completed', 'not_claimed': ['hosted CI', 'Failsafe', 'Java8 runtime', 'custom runners', 'all application suites']})
    print('Synthetic checks completed; review XML, logs and skipped reasons before claiming results.')

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        if OUT.exists():
            record(OUT / 'failure.json', {'type': type(error).__name__, 'message': str(error), 'status': 'STOPPED; no bypass attempted'})
        raise
