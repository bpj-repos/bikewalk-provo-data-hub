"""Resume a private crash update, review and complete consumer preparation from verified checkpoints."""
import argparse
from contextlib import redirect_stdout
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from danger_zones.config import HUB_ROOT as ROOT, DEFAULT_PRIVATE_DATA_ROOT
from scripts.build_catalog import checked_package, download_zip
from scripts.crash_summaries import pending_work
from scripts.review_crash_receipt import review


def read(p):
    return json.loads(Path(p).read_bytes())


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def save(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=p.parent, delete=False) as f:
        f.write((json.dumps(value, indent=2) + '\n').encode()); f.flush(); os.fsync(f.fileno())
    os.replace(f.name, p)


def inventory(folder):
    return {str(p.resolve()): sha(p) for p in sorted(folder.rglob('*')) if p.is_file() and p.name != '.adoption.lock'}


def verify_files(files):
    for name, digest in files.items():
        if not Path(name).is_file() or sha(name) != digest:
            raise ValueError('Checkpoint input/output changed: ' + name)


def code_files(consumer):
    files = {}
    for root, patterns in [(ROOT/'scripts', ('*.py', '*.cjs')), (ROOT/'pipelines/crashes/src', ('*.py',)),
                           (consumer/'scripts', ('*.py', '*.ts')), (consumer/'lib', ('crash*.ts','firebase/admin.ts')), (ROOT/'data-definitions/crashes', ('*.yml','*.json'))]:
        for pattern in patterns:
            files.update({str(p): sha(p) for p in root.rglob(pattern)})
    files[str(ROOT/'pipelines/crashes/pyproject.toml')] = sha(ROOT/'pipelines/crashes/pyproject.toml')
    return files


def latest(dataset):
    ledger = read(ROOT/'releases/release-ledger.json')
    withdrawn = {(r['dataset'], r['version']) for r in ledger['withdrawn']}
    entry = next(e for e in reversed(ledger['approved']) if e['dataset'] == dataset and (dataset,e['version']) not in withdrawn)
    folder = ROOT/'releases/datasets'/dataset/entry['version']
    checked_package(folder, entry)
    return folder, entry


def next_version(dataset):
    _, entry = latest(dataset)
    parts = list(map(int, entry['version'].split('.'))); parts[-1] += 1
    return '.'.join(map(str, parts))


class Run:
    def __init__(self, folder, request=None):
        self.folder = folder.resolve(); self.file = self.folder/'run.json'
        if not self.folder.is_relative_to(ROOT/'private'):
            raise ValueError('Use a private run directory in this checkout')
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.file.exists():
            self.state = read(self.file)
            if request is not None and request != self.state['request']:
                raise ValueError('Resume with the original request')
        else:
            if request is None: raise ValueError('Supply --request for a new run')
            allowed = {'consumer','previousExport','previousExportSha256','workbook','history','offline',
                       'portalWorkbooks','policeInputs','capturePortal','streetVersion','timeVersion','sourceRepo','annualVersion','projects'}
            if set(request)-allowed: raise ValueError('Unknown request fields')
            consumer = Path(request['consumer']).resolve()
            if not (consumer/'scripts/crash-update.py').is_file(): raise ValueError('Consumer lacks the maintained adoption command')
            inputs = {str(Path(request[k]).resolve()): sha(request[k]) for k in ('previousExport','history')}
            if not request.get('capturePortal') and not request.get('workbook'):raise ValueError('Supply workbook or capturePortal')
            if request.get('workbook'):inputs[str(Path(request['workbook']).resolve())]=sha(request['workbook'])
            if request.get('workbook'):
                inputs[str(Path(request['workbook']).with_suffix('.xlsx.json').resolve())] = sha(Path(request['workbook']).with_suffix('.xlsx.json'))
            for name in request.get('portalWorkbooks', []) + request.get('policeInputs', []): inputs[str(Path(name).resolve())] = sha(name)
            if sha(request['previousExport']) != request['previousExportSha256']: raise ValueError('Previous export checksum mismatch')
            self.state = {'schemaVersion':1, 'request':request, 'inputs':inputs, 'producerFiles':code_files(consumer), 'stages':{}}
            save(self.file, self.state)
        verify_files(self.state['inputs']); verify_files(self.state['producerFiles'])
        self.request = self.state['request']; self.consumer = Path(self.request['consumer']).resolve()

    def guard_collection(self):
        if self.state.get('reviewedCollection'):
            pointer=read(DEFAULT_PRIVATE_DATA_ROOT/'datastores/combined-incidents.json')
            if pointer['sha256']!=self.state['reviewedCollection']['sha256'] or sha(pointer['path'])!=pointer['sha256']:
                raise ValueError('Collection changed during coordination; start a new run')

    def step(self, name, fn):
        self.guard_collection()
        prior = self.state['stages'].get(name)
        if prior and prior['status'] == 'complete':
            verify_files(prior['files'])
            return prior['result']
        attempt = (prior or {}).get('attempt', 0) + 1
        work = self.folder/f'{name}-{attempt}'
        work.mkdir(mode=0o700)
        self.state['stages'][name] = {'status':'running', 'attempt':attempt}
        self.state['status'] = 'running'; self.state['stage'] = name; save(self.file,self.state)
        try:
            result = fn(work)
            self.guard_collection()
            self.state['stages'][name] = {'status':'complete', 'attempt':attempt, 'result':result, 'files':inventory(work)}
            save(self.file,self.state)
            return result
        except Exception as exc:
            self.state.update(status='failed', error=str(exc)); save(self.file,self.state)
            raise

    def command(self, work, args, cwd=ROOT):
        with (work/'stdout.json').open('w') as out, (work/'stderr.log').open('w') as err:
            result = subprocess.run(list(map(str,args)), cwd=cwd, stdout=out, stderr=err,
                                    env=dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT),str(ROOT/'pipelines/crashes/src')])) )
        if result.returncode not in (0, 2):
            raise ValueError(f'Command exited {result.returncode}; see {work}/stderr.log')
        value = read(work/'stdout.json')
        return value

    def consumer_command(self, work, action, destination, plan=None, pin=None):
        args = [sys.executable, self.consumer/'scripts/crash-update.py', action, destination]
        if plan: args += ['--plan', plan]
        if pin: args += ['--sha256', pin]
        return self.command(work,args,self.consumer)

    def prepare(self, through=None):
        request = self.request
        def intake(work):
            args = [sys.executable, '-m', 'scripts.update_crashes']
            if request.get('offline'): args += ['--offline']
            for flag, key in [('--portal-workbook','portalWorkbooks'),('--police-input','policeInputs')]:
                for p in request.get(key,[]): args += [flag,p]
            if request.get('capturePortal'):
                capture = self.step('portalCapture', lambda folder: self.capture(folder))
                args += ['--portal-workbook', capture['workbook']]
            result = self.command(work,args)
            save(work/'pointer.json', result['collection'])
            return result
        intake_result = self.step('intake', intake)
        if through == 'intake': return self.status('intake-complete')
        # Recheck readiness on every resume: drafts are reviewed outside the deterministic producer.
        ready = pending_work()
        if ready['pending']:
            self.state['summaryReview'] = ready
            return self.status('needs-summary-review')
        self.state.pop('summaryReview', None)
        pointer = read(DEFAULT_PRIVATE_DATA_ROOT/'datastores/combined-incidents.json')
        accepted = self.state.get('reviewedCollection', intake_result['collection'])
        if pointer['sha256'] != accepted['sha256']:
            # Only a completed summary application may advance this run's reviewed input.
            old = read(intake_result['collection']['path']); new = read(pointer['path'])
            from danger_zones.update_incidents import summary_basis
            if {g['id']:summary_basis(g) for g in old['records']} != {g['id']:summary_basis(g) for g in new['records']}:
                raise ValueError('Collection reporting changed; start a new run')
            if 'base' in self.state['stages']: raise ValueError('Collection changed after consumer preparation; start a new run')
        self.state['reviewedCollection'] = pointer; save(self.file,self.state)
        def baseline(work):
            stress, entry = latest('provo-bicycle-traffic-stress')
            save(work/'pointer.json', pointer)
            plan = {'hub':str(ROOT), 'pointer':str(work/'pointer.json'), 'stressPackage':str(stress),
                    'stressSha256':entry['sha256'], 'workbook':self.state['stages']['portalCapture']['result']['workbook'] if request.get('capturePortal') else request['workbook'], 'history':request['history']}
            save(work/'plan.json',plan)
            result = self.consumer_command(work,'base',work/'data',work/'plan.json')
            return {**result,'directory':str(work),'plan':plan}
        base = self.step('base', baseline)
        def comparison(work):
            result = review(work/'review', Path(request['previousExport']), request['previousExportSha256'], [],
                            Path(base['archive']), request.get('streetVersion') or next_version('provo-crash-street-membership'),
                            request.get('timeVersion') or next_version('provo-crash-occurrence-time'))
            if any(a['changedYears'] for a in result['annual'].values()):
                from scripts.prepare_crash_releases import prepare, AT
                _, current=latest(AT)
                complete=read(ROOT/'releases/datasets'/AT/current['version']/'datapackage.json')['completeThrough']
                version=request.get('annualVersion') or next_version(AT)
                prepare(Path(pointer['releaseManifest']['path']),pointer['releaseManifest']['sha256'],work/'annual',version,complete)
                package=work/'annual'/AT/version
                result['annualPackage']={'path':str(package),'dataset':AT,'version':version,'sha256':sha(package/'datapackage.json')}
                projects=Path(request.get('projects',request.get('sourceRepo',Path.home()/'Documents/ChatGPT/bikewalk-provo')))
                if not (projects/'apps/maps/scripts/hub-update.py').is_file():raise ValueError('Supply Projects checkout for changed annual data')
            return {**result,'directory':str(work/'review')}
        compared = self.step('review',comparison)
        if through == 'review': return self.status('review-ready')
        def complete(work):
            from scripts.crash_road_segments import refresh
            with redirect_stdout(sys.stderr): road = refresh(offline=True)
            plan = dict(base['plan'], roadPackage=road['path'], roadSha256=road['sha256'])
            shutil.copytree(Path(base['directory'])/'data', work/'data')
            shutil.copy2(Path(base['directory'])/'baseline.json', work/'baseline.json')
            for name, key in [('streets','street'), ('time','time')]:
                info = compared['prepared'][name]; package = Path(info['path'])
                manifest = read(package/'datapackage.json')
                files = checked_package(package,dict(dataset=manifest['name'],version=manifest['version'],sha256=info['manifestSha256']))
                prefix = f"datasets/{manifest['name']}/{manifest['version']}/"
                zipfile = work/(key+'.zip')
                zipfile.write_bytes(download_zip({prefix+k:v for k,v in files.items()},{'manifest':'/'+prefix+'datapackage.json'}))
                plan.update({key+'Zip':str(zipfile),key+'Sha256':info['manifestSha256'],key+'Package':str(package)})
            save(work/'plan.json',plan)
            self.consumer_command(work,'finish',work/'data',work/'plan.json')
            result = self.consumer_command(work,'seal',work/'data')
            return {**result,'directory':str(work),'receiptSha256':sha(work/'adoption.json'),'plan':plan}
        completed = self.step('consumer',complete)
        def concern_preview(work):
            export = Path(compared['directory'])/'details.json'
            output = self.consumer/'.artifacts'/('crash-update-'+hashlib.sha256(str(work).encode()).hexdigest()[:20])
            # The existing preview writes the immutable before/after transaction plan.
            report = self.command(work,['node','--import','tsx','scripts/import-concern-crash-details.ts','preview',
                '--file',export,'--sha256',compared['exportSHA256'],'--output',output],self.consumer)
            shutil.copytree(output,work/'backup')
            return {**report,'directory':str(work/'backup')}
        concerns=self.step('concerns',concern_preview)
        receipt=self.folder/'reviewed-adoption.json'
        approved={'collection':pointer,'consumerReceiptSha256':completed['receiptSha256'],
                  'concernBackupSha256':concerns['backupSha256'],'concernExportSha256':compared['exportSHA256'],
                  'annualPackage':compared.get('annualPackage')}
        if receipt.exists() and read(receipt)!=approved:raise ValueError('Run adoption receipt changed')
        if not receipt.exists():save(receipt,approved)
        self.state['adoption'] = {'receipt':str(receipt),'sha256':sha(receipt)}
        return self.status('prepared')

    def capture(self, work):
        subprocess.run(['node', str(ROOT/'scripts/capture_city_crash_portal.cjs'), str(work/'portal'), 'Provo'],check=True,stdout=sys.stderr)
        return {'workbook':str(work/'portal/Provo.xlsx')}

    def status(self, status):
        self.state['status']=status; self.state.pop('error',None); save(self.file,self.state)
        return {'run':str(self.folder),'status':status,'stage':self.state.get('stage'),
                **{k:self.state[k] for k in ('adoption','summaryReview') if k in self.state}}

    def apply(self, pin):
        result = self.prepare()
        if result['status'] != 'prepared': return result
        completed = self.state['stages']['consumer']['result']
        if pin != self.state['adoption']['sha256']: raise ValueError('Approve the exact adoption receipt')
        # Public package checks precede any current-file changes in the consumer checkout.
        plan = completed['plan']
        from urllib.request import urlopen
        for key in ('street','time','road'):
            package = Path(plan[key+'Package']); manifest = read(package/'datapackage.json')
            entry = dict(dataset=manifest['name'],version=manifest['version'],sha256=plan[key+'Sha256'])
            if entry not in read(ROOT/'releases/release-ledger.json')['approved']: raise ValueError('Package must be registered before adoption: '+manifest['name'])
            for name, raw in checked_package(package,entry).items():
                url=f"https://bikewalk-provo-data-hub.vercel.app/datasets/{manifest['name']}/{manifest['version']}/{name}"
                with urlopen(url,timeout=60) as response:
                    if response.read()!=raw: raise ValueError('Public package bytes differ: '+url)
        directory=Path(completed['directory'])
        adopted = self.step('apply',lambda work:self.consumer_command(work,'apply',directory/'data',pin=completed['receiptSha256']))
        verification=self.folder/'stages-verification';verification.mkdir(exist_ok=True)
        verified=self.consumer_command(verification,'verify',self.consumer/'data')
        if verified['dataset']!=completed['dataset']:raise ValueError('Consumer checkout changed after adoption')
        self.state['consumerAdoption']=adopted
        annual=self.state['stages']['review']['result'].get('annualPackage')
        if annual:
            def projects_apply(work):
                import runpy
                projects=Path(self.request.get('projects',self.request.get('sourceRepo',Path.home()/'Documents/ChatGPT/bikewalk-provo')))
                adapter=runpy.run_path(str(projects/'apps/maps/scripts/hub-update.py'))
                with redirect_stdout(sys.stderr):
                    digest=adapter['stage']('at-crashes',annual['version'])
                    report=read(adapter['REVIEWS']/digest/'review.json')
                    if report['pin']!=annual['sha256']:raise ValueError('Projects annual pin mismatch')
                    adapter['apply'](digest)
                save(work/'review.json',report)
                return {'reviewSha256':digest,'manifestSha256':annual['sha256']}
            self.step('projectsApply',projects_apply)
        preview=self.state['stages']['concerns']['result']
        self.step('concernApply',lambda work:self.command(work,['node','--import','tsx','scripts/import-concern-crash-details.ts',
            'apply','--run',preview['directory'],'--backup-sha256',preview['backupSha256']],self.consumer))
        return self.status('adopted-awaiting-deployment')

    def packages(self):
        plan=self.state['stages']['consumer']['result']['plan']
        for key in ('street','time','road'):
            folder=Path(plan[key+'Package']); manifest=read(folder/'datapackage.json')
            entry={'dataset':manifest['name'],'version':manifest['version'],'sha256':plan[key+'Sha256']}
            yield folder,entry,checked_package(folder,entry)

        annual=self.state['stages']['review']['result'].get('annualPackage')
        if annual:
            entry={k:annual[k] for k in ('dataset','version','sha256')}
            yield Path(annual['path']),entry,checked_package(Path(annual['path']),entry)

    def register(self,pin):
        result=self.prepare()
        if result['status']!='prepared':return result
        if pin!=self.state['adoption']['sha256']:raise ValueError('Approve the exact adoption receipt')
        ledger_path=ROOT/'releases/release-ledger.json'
        with (ROOT/'private/crash-release.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            ledger=read(ledger_path)
            for folder,entry,files in self.packages():
                if any(w['dataset']==entry['dataset'] and w['version']==entry['version'] for w in ledger['withdrawn']):
                    raise ValueError('Cannot register a withdrawn version')
                old=next((e for e in ledger['approved'] if e['dataset']==entry['dataset'] and e['version']==entry['version']),None)
                if old and old!=entry:raise ValueError('Version already registered with different bytes')
                target=ROOT/'releases/datasets'/entry['dataset']/entry['version']
                if target.exists():
                    if checked_package(target,entry)!=files:raise ValueError('Release bytes differ')
                else:
                    target.parent.mkdir(parents=True,exist_ok=True)
                    with tempfile.TemporaryDirectory(dir=target.parent) as temp:
                        staged=Path(temp)/'package';staged.mkdir()
                        for name,raw in files.items():(staged/name).write_bytes(raw)
                        staged.rename(target)
                if not old:ledger['approved'].append(entry)
            save(ledger_path,ledger)
        return self.status('registered-awaiting-commit')

    def publish(self,pin):
        result=self.prepare()
        if result['status']!='prepared':return result
        if pin!=self.state['adoption']['sha256']:raise ValueError('Approve the exact adoption receipt')
        from scripts.publish_route_update import cmd, git, stage_url, unchanged_head
        from scripts.build_catalog import build
        def logged(args,cwd):
            raw=cmd(args,cwd,output=True)
            if raw:print(raw.decode(),file=sys.stderr,end='')
        for _,entry,files in self.packages():
            if entry not in read(ROOT/'releases/release-ledger.json')['approved']:raise ValueError('Register packages first')
            if checked_package(ROOT/'releases/datasets'/entry['dataset']/entry['version'],entry)!=files:raise ValueError('Registered release differs')
        # Publication requires the reviewed package bytes already recorded in Git.
        if git(ROOT,'status','--porcelain','--','releases'):
            raise ValueError('Commit and push registered releases before publication')
        unchanged_head(ROOT)
        state_path=self.folder/'publication.json'
        state=read(state_path) if state_path.exists() else {}
        ledger_pin=sha(ROOT/'releases/release-ledger.json')
        if state and state['ledgerSha256']!=ledger_pin:raise ValueError('Catalog changed during publication; start a new run')
        state['ledgerSha256']=ledger_pin
        stage=self.folder/'catalog'
        if not stage.exists():
            with tempfile.TemporaryDirectory(dir=self.folder) as temp:
                build(Path(self.request.get('sourceRepo',Path.home()/'Documents/ChatGPT/bikewalk-provo')),Path(temp)/'catalog')
                (Path(temp)/'catalog').rename(stage)
        if not state.get('url'):
            logged(['vercel','link','--yes','--project','bikewalk-provo-data-hub','--scope=brycepjs-projects'],stage)
            state['url']=stage_url(stage,'bikewalk-provo-data');save(state_path,state)
        logged([sys.executable,ROOT/'scripts/verify_public_catalog.py',stage/'public','--stage',state['url']],stage)
        if not state.get('promoted'):
            unchanged_head(ROOT)
            logged(['vercel','promote',state['url'],'--yes','--scope=brycepjs-projects'],stage)
            state['promoted']=True;save(state_path,state)
        logged([sys.executable,ROOT/'scripts/verify_public_catalog.py',stage/'public'],stage)
        state['liveVerified']=True;save(state_path,state)
        return self.status('published-awaiting-adoption')

    def verify_live(self):
        from urllib.request import urlopen
        from datetime import datetime,timezone
        completed=self.state['stages']['consumer']['result']
        def get(path):
            with urlopen('https://www.provostreets.watch'+path,timeout=60) as r:return json.load(r)
        live=get('/api/crash-map')
        if live['dataset']!=completed['dataset']:raise ValueError('Consumer deployment has not adopted this dataset')
        staged=read(Path(completed['directory'])/'data/crash-stress/map.json')
        if live['counts']!=staged['counts']:raise ValueError('Live crash counts differ')
        expected={f['properties']['id']:f for f in staged['features'] if f['properties']['kind']=='crash'}
        actual={f['properties']['id']:f for f in live['features'] if f['properties']['kind']=='crash'}
        if set(expected)!=set(actual):raise ValueError('Live membership differs')
        for key,row in expected.items():
            if row['geometry']!=actual[key]['geometry'] or any(actual[key]['properties'].get(k)!=v for k,v in row['properties'].items()):
                raise ValueError('Live crash facts differ')
        example=next(iter(expected))
        detail=get('/api/crash-map/details?dataset='+live['dataset']+'&id='+example)
        if not detail.get('summary',{}).get('brief') or 'derived' not in detail:raise ValueError('Live detail companions unavailable')
        preview=self.state['stages']['concerns']['result']
        backup=read(Path(preview['directory'])/'backup.json')
        for plan in backup['concerns']:
            if get('/api/concerns/'+plan['id'])['crashHistory']!=plan['after']:raise ValueError('Live concern adoption differs')
        annual=self.state['stages']['review']['result'].get('annualPackage')
        if annual:
            with urlopen('https://projects.bikewalkprovo.org/release.json',timeout=60) as response: projects=json.load(response)
            if projects.get('crashDatasets',{}).get(annual['dataset'])!={'version':annual['version'],'sha256':annual['sha256']}:
                raise ValueError('Projects annual deployment has not adopted this pin')
        self.state['liveVerification']={'verifiedAt':datetime.now(timezone.utc).isoformat(),'dataset':live['dataset'],'crashes':len(expected),'concerns':len(backup['concerns'])}
        return self.status('live-verified')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['prepare','register','publish','apply','verify-live','status'])
    p.add_argument('run',type=Path); p.add_argument('--request',type=Path)
    p.add_argument('--through',choices=['intake','review']); p.add_argument('--sha256')
    a=p.parse_args(); os.umask(0o077)
    if not a.run.resolve().is_relative_to(ROOT/'private'):p.error('Use a private run directory in this checkout')
    a.run.mkdir(parents=True,exist_ok=True,mode=0o700)
    try:
        with (a.run/'.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            run=Run(a.run,read(a.request) if a.request else None)
            with redirect_stdout(sys.stderr):
                result=(run.prepare(a.through) if a.command=='prepare' else getattr(run,a.command)(a.sha256)
                        if a.command in ('register','publish','apply') else run.verify_live() if a.command=='verify-live' else run.state)
        print(json.dumps(result,indent=2))
        sys.exit(2 if result['status']=='needs-summary-review' else 0)
    except Exception as exc:
        print(json.dumps({'status':'failed','run':str(a.run),'error':str(exc), 'stage':run.state.get('stage') if 'run' in locals() else 'preflight'})); sys.exit(1)
