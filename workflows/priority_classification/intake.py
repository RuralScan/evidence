"""Validate and stage cross-cutting candidates; no registration or scientific acceptance."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import jsonschema
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'workflows/acquisition'))
from identity import replay_metadata, verify_document
ALLOWED_VARIABLES = {'drought_hazard','water_stress','iplc_lands','carbon_sequestration_potential'}

def require(ok, message):
    if not ok: raise ValueError(message)

def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n').encode()

def digest(value): return sha256(encoded(value)).hexdigest()

def safe_path(root, path):
    require(isinstance(path,str) and not Path(path).is_absolute() and '..' not in Path(path).parts, 'Unsafe repository path')
    target=(root/path).resolve()
    require(target.is_relative_to(root.resolve()), 'Path escapes repository')
    return target

def no_method_fields(value):
    if isinstance(value,dict):
        require(not ({'class_scores','classification_scores','weight_default','accepted_rule','nbs_id','suitability_family_id','use_role'} & set(value)), 'Method scores or fabricated practice lane in finding')
        for child in value.values(): no_method_fields(child)
    elif isinstance(value,list):
        for child in value: no_method_fields(child)

def validate(bundle, root=ROOT):
    manifest=json.loads((root/'registers/cross_cutting/manifest.json').read_text())
    require(manifest['activation']=='disabled' and manifest['status']=='proposed_not_activated' and manifest['canonical_record_count']==0, 'Canonical activation is not implemented')
    for path in manifest['proposed_stores'].values():
        require(not safe_path(root,path).exists(), 'Canonical writes require a protected registration adapter')
    schema_ref=manifest['candidate_schema'];schema_path=safe_path(root,schema_ref['path'])
    require(sha256(schema_path.read_bytes()).hexdigest()==schema_ref['sha256'],'Stale candidate schema manifest')
    jsonschema.Draft202012Validator(json.loads(schema_path.read_text())).validate(bundle)
    require(sha256(safe_path(root,bundle['instruction_ref']).read_bytes()).hexdigest()==bundle['instruction_sha256'],'Changed extraction protocol')
    search_path=safe_path(root,bundle['search_ref'])
    require(sha256(search_path.read_bytes()).hexdigest()==bundle['search_sha256'],'Changed search log')
    search=json.loads(search_path.read_text())
    require(search['total_sources']==len(bundle['sources']) and search['total_sources']<=search['source_cap'],'Search source count/cap mismatch')
    for run in search['searches']:
        from collections import Counter
        require(run['returned']==run['screened']==len(run['results']),'Search counts differ from visible screened records')
        require(run['dispositions']==dict(Counter(r['disposition'] for r in run['results'])),'Search dispositions do not reconcile')
    sources={s['candidate_source_id']:s for s in bundle['sources']}
    require(len(sources)==len(bundle['sources']),'Duplicate source version')
    require(len({f['candidate_finding_id'] for f in bundle['findings']})==len(bundle['findings']),'Duplicate finding version')
    for path, expected in bundle['packet_dependencies'].items():
        require(path.startswith('workflows/priority_classification/packets/'), 'Invalid packet dependency path')
        require(sha256(safe_path(root,path).read_bytes()).hexdigest()==expected,'Changed original source packet')
    for source in sources.values():
        ref=source['identity_receipt'];p=safe_path(root,ref['path'])
        require(p.name=='receipt.json' and 'acquisition' in p.parts,'Unexpected receipt location')
        require(sha256(p.read_bytes()).hexdigest()==ref['sha256'],'Changed acquisition receipt')
        receipt=json.loads(p.read_text());candidate=json.loads(p.with_name('candidate.json').read_text());plan=json.loads(p.with_name('plan.json').read_text())
        raw_hash=lambda x:sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
        require(receipt['candidate_sha256']==raw_hash(candidate) and receipt['plan_sha256']==raw_hash(plan),'Changed acquisition inputs')
        require(receipt['status']=='acquired' and receipt['document']['verified'],'Unverified source identity')
        require(replay_metadata(candidate,receipt['metadata'])==receipt['metadata'],'Metadata identity replay failed')
        require(source['title']==receipt['metadata']['title'] and source['citation']==receipt['metadata']['citation'] and source['doi']==(receipt['metadata']['doi'] or None),'Source citation differs from verified identity')
        require(source['candidate_source_id']=='xcs_'+receipt['candidate_id'],'Source identity mismatch')
        require(source['url']==candidate['url'] and source['artifact']['acquisition_url']==receipt['artifact']['url'] and source['artifact']['sha256']==receipt['artifact']['sha256'],'Source artefact mismatch')
        require(source['artifact']['media_type']==('application/pdf' if receipt['kind']=='pdf' else 'text/html'),'Wrong artefact type')
    for finding in bundle['findings']:
        require(finding['candidate_source_id'] in sources,'Unresolved finding source')
        require(set(finding['variables'])<=ALLOWED_VARIABLES,'Outside bounded T5 scope')
        source=sources[finding['candidate_source_id']]
        require(finding['locator']['type']==('pdf_page' if source['artifact']['media_type']=='application/pdf' else 'section'),'Locator/format mismatch')
        no_method_fields(finding)
    return {'candidate_sha256':digest(bundle),'sources':len(sources),'findings':len(bundle['findings']),'registered_sources':0,'registered_findings':0,'accepted_classifications':0}

def verify_private_artifacts(bundle, locations, root=ROOT):
    validate(bundle,root);by_id={r['candidate_source_id']:r for r in locations}
    for source in bundle['sources']:
        folder=Path(by_id[source['candidate_source_id']]['private_directory'])
        matches=[p for p in folder.iterdir() if p.is_file() and sha256(p.read_bytes()).hexdigest()==source['artifact']['sha256']]
        require(matches,'Pinned original not found in private cache')
        kind='pdf' if source['artifact']['media_type']=='application/pdf' else 'website'
        require(verify_document(matches[0].read_bytes(),kind,source['title'])['verified'],'Private original title check failed')

def review_projection(findings, events):
    """Pure replay prototype. A PR-shaped reference does not authenticate a human."""
    known={f['candidate_finding_id']:f for f in findings};state={k:'unreviewed' for k in known};seen={};sequence={k:0 for k in known}
    for event in events:
        require(set(event)=={'event_id','finding_id','finding_sha256','sequence','action','reviewer','reason','review_ref'},'Invalid review event')
        if event['event_id'] in seen:
            require(seen[event['event_id']]==event,'Conflicting retry');continue
        fid=event['finding_id'];require(fid in known and event['finding_sha256']==digest(known[fid]),'Review targets changed or unknown finding')
        require(type(event['sequence']) is int and event['sequence']==sequence[fid]+1,'Invalid review sequence')
        require(event['action'] in {'keep','drop','query','reopen'} and event['reviewer'] and event['reason'],'Incomplete source review')
        require(re.fullmatch(r'https://github.com/RuralScan/evidence/pull/[0-9]+',event['review_ref']) is not None,'Review requires a protected PR reference')
        state[fid]={'keep':'kept','drop':'dropped','query':'queried','reopen':'unreviewed'}[event['action']]
        seen[event['event_id']]=event;sequence[fid]=event['sequence']
    return state

def stage(bundle, out, root=ROOT):
    result=validate(bundle,root);out.mkdir(parents=True,exist_ok=True)
    path=out/(result['candidate_sha256']+'.json');data=encoded(bundle)
    if path.exists(): require(path.read_bytes()==data,'Immutable candidate was altered')
    else:
        with path.open('xb') as stream:stream.write(data)
    return path

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['check','stage']);parser.add_argument('candidate',type=Path);parser.add_argument('--out',type=Path);parser.add_argument('--artifact-locations',type=Path)
    args=parser.parse_args();bundle=json.loads(args.candidate.read_text());result=validate(bundle)
    if args.artifact_locations:verify_private_artifacts(bundle,json.loads(args.artifact_locations.read_text()));result['private_originals_verified']=True
    if args.command=='stage':
        require(args.out is not None,'stage requires --out');result['candidate_path']=str(stage(bundle,args.out))
    print(json.dumps(result,sort_keys=True))
if __name__=='__main__': main()
