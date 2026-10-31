#!/usr/bin/env python3
"""Synthetic migration fixture. Standard library only; no credential or TLS changes."""
import hashlib, json, os, pathlib, shutil, subprocess, sys, zipfile, signal
ROOT = pathlib.Path(__file__).resolve().parent
WORK = ROOT / 'work'
LOGS = ROOT / 'evidence'
VERSIONS = {'baseline': '9.0.123', 'target': '10.1.61'}
RESULTS = []

def run(name, args, expected=0, contains=None, forbidden=()):
    process = subprocess.Popen([str(a) for a in args], cwd=ROOT,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, start_new_session=True)
    timed_out = False
    try:
        output, _ = process.communicate(timeout=180)
    except subprocess.TimeoutExpired:
        timed_out = True
        # Only this subprocess's new session/process group belongs to this step.
        try: os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError: pass
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            output, _ = process.communicate()
        # Kill any remaining descendants even if the group leader exited on TERM.
        try: os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
    code = process.returncode
    (LOGS / (name + '.log')).write_text('$ ' + ' '.join(map(str,args)) + '\n' + output
        + ('\nSTEP_TIMEOUT after 180 seconds\n' if timed_out else ''))
    ok = code == expected if expected == 0 else code != 0
    ok = not timed_out and ok and (contains is None or contains in output) and not any(text in output for text in forbidden)
    RESULTS.append({'step': name, 'exit': code, 'timed_out': timed_out, 'passed': ok})
    (LOGS / 'results.json').write_text(json.dumps(RESULTS, indent=2))
    print(name, 'PASS' if ok else 'FAIL', flush=True)
    if not ok: raise RuntimeError('Inspect evidence/' + name + '.log')
    return output

def archive(path, entries):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as out:
        for name, data in entries.items(): out.writestr(name, data)

def files_below(path):
    return {str(p.relative_to(path)): p.read_bytes() for p in path.rglob('*') if p.is_file()}

def build(profile):
    p = WORK / profile
    ns = 'javax' if profile == 'baseline' else 'jakarta'
    p.mkdir(parents=True)
    pom = f'''<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion><groupId>example</groupId>
  <artifactId>namespace-probe-{profile}</artifactId><version>1.0</version>
  <dependencies><dependency><groupId>org.apache.tomcat.embed</groupId>
  <artifactId>tomcat-embed-core</artifactId><version>{VERSIONS[profile]}</version>
  </dependency></dependencies></project>'''
    (p/'pom.xml').write_text(pom)
    run(profile+'-dependencies', ['mvn','-B','-f',p/'pom.xml',
        'org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies',
        '-DoutputDirectory='+str(p/'deps')])
    run(profile+'-dependency-tree', ['mvn','-B','-f',p/'pom.xml',
        'org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree'])
    cp = os.pathsep.join(str(f) for f in sorted((p/'deps').glob('*.jar')))
    assert cp, 'No resolved runtime jars'
    for kind in ('shared','web','runner'):
        dest=p/'src'/kind; dest.mkdir(parents=True)
        for src in (ROOT/'src'/kind).glob('*.java'):
            text=src.read_text()
            # The reviewed allowlist is javax.servlet only. javax.sql must survive.
            if profile == 'target': text=text.replace('javax.servlet.', 'jakarta.servlet.')
            (dest/src.name).write_text(text)
        classes=p/'classes'/kind; classes.mkdir(parents=True)
        classpath=cp + (os.pathsep+str(p/'shared.jar') if kind=='web' else '')
        run(profile+'-compile-'+kind, ['javac','--release','17','-cp',classpath,
            '-d',classes,*sorted(dest.glob('*.java'))])
        if kind=='shared':
            entries=files_below(classes)
            entries['META-INF/services/'+ns+'.servlet.ServletContainerInitializer']=b'demo.Startup\n'
            archive(p/'shared.jar',entries)
    entries={'WEB-INF/classes/'+k:v for k,v in files_below(p/'classes'/'web').items()}
    entries['WEB-INF/lib/shared.jar']=(p/'shared.jar').read_bytes()
    entries['WEB-INF/classes/probe.properties']=('request.api='+ns+'.servlet.ServletRequest\n').encode()
    xmlns='http://xmlns.jcp.org/xml/ns/javaee' if profile=='baseline' else 'https://jakarta.ee/xml/ns/jakartaee'
    ver='4.0' if profile=='baseline' else '6.0'
    entries['WEB-INF/web.xml']=f'''<web-app xmlns="{xmlns}" version="{ver}">
  <servlet><servlet-name>probe</servlet-name><servlet-class>demo.ProbeServlet</servlet-class></servlet>
  <servlet-mapping><servlet-name>probe</servlet-name><url-pattern>/probe</url-pattern></servlet-mapping>
</web-app>'''.encode()
    archive(p/'probe.war',entries)
    (p/'classpath.txt').write_text(cp)
    return p, entries

def probe(name,p,war,status,body):
    cp=str(p/'classes'/'runner')+os.pathsep+(p/'classpath.txt').read_text()
    run(name,['java','-cp',cp,'demo.ProbeRunner',war,str(status),body],contains='PROBE_PASS',forbidden=('SEVERE:', 'Exception fixing docBase', 'org.apache.jasper.servlet.JspServlet'))

def main():
    if not __debug__: raise SystemExit('Python optimization must be disabled; do not use -O or PYTHONOPTIMIZE.')
    if WORK.exists(): raise SystemExit('Refusing to overwrite work/. Move this fixture to a fresh directory to rerun.')
    LOGS.mkdir(exist_ok=True)
    for cmd in ('java','javac','mvn'):
        if not shutil.which(cmd): raise SystemExit('Missing prerequisite: '+cmd)
    java=run('java-version',['java','-version'])
    if 'version "17.' not in java: raise SystemExit('Select existing JDK17 with process-local JAVA_HOME/PATH, then rerun in a fresh directory.')
    run('maven-version',['mvn','-version'])
    baseline,_=build('baseline')
    target,entries=build('target')
    good='name=pilot;sql=javax.sql.DataSource;initializer=discovered'
    probe('baseline-runtime',baseline,baseline/'probe.war',200,good)
    probe('target-runtime',target,target/'probe.war',200,good)
    # Negative 1: demonstrate why a global javax replacement is invalid.
    bad=WORK/'BadSql.java';bad.write_text('import jakarta.sql.DataSource; class BadSql { DataSource source; }\n')
    run('negative-java-se',['javac','--release','17','-d',WORK/'bad-classes',bad],expected=1,contains='package jakarta.sql does not exist')
    # Negative 2: unchanged reflective configuration is compiled into no import.
    changed=dict(entries);changed['WEB-INF/classes/probe.properties']=b'request.api=javax.servlet.ServletRequest\n'
    archive(target/'stale-property.war',changed)
    probe('negative-property',target,target/'stale-property.war',500,'REFLECTION_MISSING=javax.servlet.ServletRequest')
    # Negative 3: service-provider file names are part of the migration.
    with zipfile.ZipFile(target/'shared.jar') as jar: shared={n:jar.read(n) for n in jar.namelist()}
    data=shared.pop('META-INF/services/jakarta.servlet.ServletContainerInitializer')
    shared['META-INF/services/javax.servlet.ServletContainerInitializer']=data
    archive(target/'stale-service.jar',shared)
    changed=dict(entries);changed['WEB-INF/lib/shared.jar']=(target/'stale-service.jar').read_bytes()
    archive(target/'stale-service.war',changed)
    probe('negative-service',target,target/'stale-service.war',200,'name=pilot;sql=javax.sql.DataSource;initializer=null')
    # Negative 4: preserve modern initializer but replace the public library binary.
    with zipfile.ZipFile(target/'shared.jar') as jar: shared={n:jar.read(n) for n in jar.namelist()}
    with zipfile.ZipFile(baseline/'shared.jar') as jar: shared['demo/RequestLabel.class']=jar.read('demo/RequestLabel.class')
    archive(target/'stale-binary.jar',shared)
    changed=dict(entries);changed['WEB-INF/lib/shared.jar']=(target/'stale-binary.jar').read_bytes()
    archive(target/'stale-binary.war',changed)
    probe('negative-binary',target,target/'stale-binary.war',500,'LINKAGE_ERROR=NoSuchMethodError|LINKAGE_ERROR=NoClassDefFoundError')
    # Contents audit: container APIs are on the runner classpath, not bundled in WAR.
    assert set(n for n in entries if n.startswith('WEB-INF/lib/')) == {'WEB-INF/lib/shared.jar'}
    assert b'javax.sql.DataSource' in (target/'src'/'shared'/'RequestLabel.java').read_bytes()
    print('ALL_CHECKS_PASS',flush=True)
    (LOGS/'artifact-hashes.json').write_text(json.dumps({str(p.relative_to(WORK)):hashlib.sha256(p.read_bytes()).hexdigest() for p in WORK.rglob('*') if p.is_file() and p.suffix in ('.war','.jar','.java','.xml')},indent=2))

if __name__ == '__main__': main()
