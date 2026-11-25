"""Validate preserved candidate observations for the single priority store. No review ledger."""
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
    schema_path=root/'workflows/priority_classification/candidate-schema.json'
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

