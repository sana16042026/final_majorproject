"""End-to-end checks for both supported master formats and every risk contribution."""
from pathlib import Path
import os,sys,argparse,json,subprocess,compileall
from concurrent.futures import ThreadPoolExecutor
P=Path(__file__).resolve().parent
if P.name=='checks':P=P.parent
sys.path.insert(0,str(P))
parser=argparse.ArgumentParser()
parser.add_argument('--database')
parser.add_argument('--import-both',action='store_true')
args=parser.parse_args()
if args.database:os.environ['DB_NAME']=args.database
import pandas as pd
from config import Config
from init_db import init_database
from db import query_db
from app import app
from services.data_processor import load_and_validate_file,clean_and_normalize_data
from models.risk_engine import calculate_project_risk
from models.duplicate_engine import build_duplicate_lookup

checks=[]
def check(ok,label):
    assert ok,label
    checks.append(label);print('PASS',label,flush=True)
def admin():
    client=app.test_client()
    with client.session_transaction() as session:session['user']=dict(user_id=1,username='admin',full_name='Administrator',role='district_admin',district=None,mp_id=None,vendor_id=None)
    return client
def main():
    app.config['TESTING']=True
    xlsx=Path(Config.MASTER_DATASET);csv=xlsx.with_suffix('.csv')
    raw=pd.read_excel(xlsx);rawcsv=pd.read_csv(csv)
    pd.testing.assert_frame_equal(raw,rawcsv,check_dtype=False)
    check(raw.shape==(15000,24) and raw.Work_ID.is_unique,'Excel and CSV contain identical 15000 works and 24 columns')
    check(not {'Latitude','Longitude'} & set(raw.columns),'GPS columns are absent from both datasets')
    check(not raw.astype(str).apply(lambda c:c.str.contains(r'\bsynthetic\b',case=False,regex=True).any()).any(),'Repeated display label remains removed')
    mapped=[]
    for file in [xlsx,csv]:
        frame,error=load_and_validate_file(str(file));check(error is None,'Importer accepts '+file.suffix)
        mapped.append(clean_and_normalize_data(frame,as_of='2026-10-29').drop(columns=['source_json']))
    pd.testing.assert_frame_equal(mapped[0],mapped[1],check_dtype=False)
    check(True,'Both formats produce identical normalized calculations')
    init_database();client=admin()
    if args.import_both:
        for file in [csv,xlsx]:
            with file.open('rb') as stream:response=client.post('/api/upload',data={'file':(stream,file.name)},content_type='multipart/form-data')
            result=response.get_json()
            check(response.status_code==200 and result['success'] and result['total_projects']==15000,'Full multipart '+file.suffix+' upload and all analysis modules')
            check(query_db('SELECT COUNT(*) n FROM road_projects',one=True)['n']==15000,'Unique persisted count after '+file.suffix+' upload')
    rows=query_db('SELECT * FROM road_projects ORDER BY work_id')
    check(len(rows)==15000,'Application contains exactly 15000 works')
    source={r.Work_ID:r for r in raw.itertuples()}
    check(all(len(json.loads(r['source_json']))==24 and 'Latitude' not in json.loads(r['source_json']) and 'Longitude' not in json.loads(r['source_json']) for r in rows),'All 24 source fields preserved without GPS keys')
    check(all(r['latitude'] is None and r['longitude'] is None for r in rows),'Optional legacy database coordinate fields remain empty')
    check(all(r['work_title']==source[r['work_id']].Work_Title and r['mp_id']==source[r['work_id']].Elected_MP for r in rows),'Cleaned names are preserved in stored projects')
    as_of=pd.Timestamp(rows[0]['analysis_as_of'])
    dates=pd.to_datetime(raw.Completion_Date,errors='coerce',format='mixed')
    expected=pd.to_datetime(raw.Expected_Completion_Date,errors='coerce',format='mixed')
    delay=(dates.where(dates.notna(),as_of)-expected).dt.days.clip(lower=0)
    by_id={r['work_id']:r for r in rows}
    check(all(by_id[k]['delay_days']==int(v) for k,v in zip(raw.Work_ID,delay)),'All 15000 delays independently match source-date arithmetic')
    check(all(abs(r['actual_expenditure']-source[r['work_id']].Expenditure_Amount_INR_Crore*10_000_000)<.01 for r in rows),'All currency conversions remain correct')
    ml={r['work_id']:r for r in query_db('SELECT * FROM ml_analysis')}
    risks={r['work_id']:r for r in query_db('SELECT * FROM risk_analysis')}
    duplicates=query_db('SELECT * FROM duplicate_analysis ORDER BY evidence_score DESC, pair_id ASC')
    lookup=build_duplicate_lookup(duplicates)
    maxima={'financial_anomaly':25,'cost_overrun':25,'delay':25,'progress_gap':10,'duplicate':20,'bidders':10,'expenditure_ratio':15}
    check(len(ml)==len(risks)==15000,'Financial and risk analyses exist for every work')
    for r in rows:
        calculated=calculate_project_risk(r,ml.get(r['work_id']),[],lookup.get(r['work_id'],[]))
        assert calculated['risk_score']==risks[r['work_id']]['risk_score'],r['work_id']
        assert calculated['risk_level']==risks[r['work_id']]['risk_level'],r['work_id']
        components=calculated['risk_breakdown']
        assert {c['key']:c['maximum_points'] for c in components}==maxima
        assert all(0<=c['points']<=c['maximum_points'] for c in components)
        assert sum(c['points'] for c in components)==calculated['uncapped_score']
        assert min(100,calculated['uncapped_score'])==calculated['risk_score']
    check(True,'All 15000 stored risk scores reconcile with all seven graded parameters and the cap')
    check(all(by_id[d['work_id_1']]['state']==by_id[d['work_id_2']]['state'] and by_id[d['work_id_1']]['district']==by_id[d['work_id_2']]['district'] for d in duplicates),'All contextual duplicate pairs remain inside the same state and district')
    for url in ['/','/projects','/upload','/financial-analysis','/similar-works','/risk-analysis','/reports?work_id=R-00001']:
        check(client.get(url).status_code==200,'Page renders '+url)
    manifest=json.loads((P/'data/DATASET_COVERAGE.json').read_text(encoding='utf-8'))
    check(set(client.get('/api/filters').get_json()['states'])=={c['state'] for c in manifest['coverage']},'All 28 states are available in filters')
    def verify_state(cov):
        c=admin();state=cov['state']
        filters=c.get('/api/filters',query_string={'state':state}).get_json()
        check(set(filters['districts'])==set(cov['districts']),'State and district options: '+state)
        listing=c.get('/api/projects',query_string={'state':state,'limit':2}).get_json()
        check(listing['total']==cov['records'],'Balanced state record count: '+state)
        for district,count in cov['districts'].items():
            listing=c.get('/api/projects',query_string={'state':state,'district':district,'limit':2}).get_json()
            check(listing['total']==count and all(p['state']==state and p['district']==district for p in listing['projects']),'District filter: '+state+' / '+district)
        work=raw.loc[raw.State==state,'Work_ID'].iloc[0]
        detail=c.get('/api/projects/'+work).get_json()['data']
        report=c.get('/api/reports/project/'+work).get_json()['report']
        for response in [detail,report]:
            assert response['risk_breakdown']['matches_stored_score']
            assert {row['key']:row['maximum_points'] for row in response['risk_breakdown']['components']}==maxima
        check(True,'Details and report display current score maxima: '+state)
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(verify_state,manifest['coverage']))
    check(client.get('/api/reports/project/R-00001/download').status_code==200,'Project report download works')
    dashboard=client.get('/api/dashboard').get_json()
    check(dashboard['cards']['total_projects']==15000 and sum(dashboard['charts']['risk_chart']['data'])==15000,'Dashboard totals and risk chart reflect rebuilt results')
    for path in ['/api/predictions/summary','/api/predictions/projects']:
        check(client.get(path).status_code==404,'Removed prediction endpoint stays retired '+path)
    citizen=app.test_client();citizen.post('/login',data={'username':'citizen','password':'citizen123'})
    check(citizen.get('/api/risk-analysis').status_code==403,'Citizen cannot access restricted risk analysis')
    for file in (P/'static/js').glob('*.js'):subprocess.run(['node','--check',str(file)],check=True,capture_output=True)
    check(all(compileall.compile_file(str(file),quiet=1) for folder in [P,P/'models',P/'services'] for file in folder.glob('*.py')),'Runtime Python and JavaScript syntax pass')
    result=dict(passed=len(checks),checks=checks,database=Config.DB_NAME,records=15000,columns=24,states=28,districts=138,risk_maxima=maxima,analysis_as_of=str(as_of.date()),both_formats_uploaded=args.import_both)
    out=P/'checks';out.mkdir(exist_ok=True)
    (out/('E2E_RESULTS.json' if args.import_both else 'LOCAL_VERIFICATION.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='checks'},indent=2))

if __name__=='__main__':main()
