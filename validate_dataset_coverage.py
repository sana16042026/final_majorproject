"""Read-only workbook, MySQL and Flask checks for the balanced synthetic dataset."""
from pathlib import Path
import json
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
from urllib.parse import urlencode
from config import Config
from app import app
from db import query_db

P=Path(__file__).resolve().parent
checks=[]
def check(ok,label):
    assert ok,label
    checks.append(label)
    print('PASS',label,flush=True)

def main():
    manifest=json.loads((P/'data/DATASET_COVERAGE.json').read_text(encoding='utf-8'))
    raw=pd.read_excel(Config.MASTER_DATASET)
    check(len(raw)==15000 and raw.Work_ID.is_unique,'Workbook contains exactly 15000 unique works')
    check(raw.State.nunique()==28 and raw.groupby(['State','District']).ngroups==138,'Workbook covers 28 states and 138 state/district combinations')
    check(raw.Progress_Basis.str.startswith('SYNTHETIC').all(),'Every source row is clearly labelled synthetic')
    check(raw.Latitude.isna().all() and raw.Longitude.isna().all(),'No fabricated GPS coordinates')
    app.config['TESTING']=True
    client=app.test_client()
    check(client.post('/login',data={'username':'admin','password':'admin123'}).status_code==302,'Administrator login')
    states=client.get('/api/filters').get_json()['states']
    check(set(states)=={c['state'] for c in manifest['coverage']},'State dropdown exposes all 28 populated states')
    db_rows=query_db('SELECT * FROM road_projects ORDER BY work_id')
    check(len(db_rows)==15000,'Application database contains the balanced 15000-record snapshot')
    by_id={r['work_id']:r for r in db_rows}
    check(all(by_id[r.Work_ID]['state']==r.State and by_id[r.Work_ID]['district']==r.District and by_id[r.Work_ID]['description']==r.Work_Description for r in raw.itertuples()),'All persisted locations and descriptions match the workbook')
    check(all(json.loads(by_id[r.Work_ID]['source_json'])['Progress_Basis'].startswith('SYNTHETIC') for r in raw.itertuples()),'Database retains synthetic provenance in source JSON')
    check(all(r['latitude'] is None and r['longitude'] is None for r in db_rows),'Database GPS fields remain unavailable')
    def verify_state(cov):
        client=app.test_client()
        with client.session_transaction() as session:
            session['user']=dict(user_id=1,username='admin',full_name='Administrator',role='district_admin',district=None,mp_id=None,vendor_id=None)
        state=cov['state']; rows=raw[raw.State==state]
        check(len(rows)==cov['records'] and rows.District.value_counts().to_dict()==cov['districts'],'Balanced workbook allocation: '+state)
        filters=client.get('/api/filters',query_string={'state':state}).get_json()
        check(set(filters['districts'])==set(cov['districts']),'Correct district dropdown: '+state)
        listing=client.get('/api/projects',query_string={'state':state,'limit':5}).get_json()
        check(listing['total']==cov['records'] and all(r['state']==state for r in listing['projects']),'State project filter: '+state)
        for district,count in cov['districts'].items():
            listing=client.get('/api/projects',query_string={'state':state,'district':district,'limit':3}).get_json()
            check(listing['total']==count and all(r['state']==state and r['district']==district for r in listing['projects']),'District project filter: '+state+' / '+district)
        work_id=rows.Work_ID.iloc[0]
        details=client.get('/api/projects/'+work_id).get_json()['data']
        breakdown=details['risk_breakdown']
        check(len(breakdown['components'])==7 and breakdown['matches_stored_score'] and min(100,sum(c['points'] for c in breakdown['components']))==breakdown['calculated_score'],'Risk points reconcile: '+state)
        report=client.get('/api/reports/project/'+work_id).get_json()['report']
        check(report['project']['state']==state and report['project']['district']==rows.District.iloc[0] and report['project']['delay_days']==by_id[work_id]['delay_days'],'Report reflects new geography and actual delay: '+state)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(verify_state,manifest['coverage']))
    counts=raw.State.value_counts()
    check((counts==536).sum()==20 and (counts==535).sum()==8,'State counts differ by at most one')
    check(query_db('SELECT COUNT(*) n FROM ml_analysis',one=True)['n']==15000 and query_db('SELECT COUNT(*) n FROM risk_analysis',one=True)['n']==15000,'Financial and risk analyses rebuilt for every work')
    check(query_db('SELECT COUNT(*) n FROM duplicate_analysis a JOIN road_projects p ON a.work_id_1=p.work_id JOIN road_projects q ON a.work_id_2=q.work_id WHERE p.state<>q.state OR p.district<>q.district',one=True)['n']==0,'Every contextual duplicate pair stays inside the same state and district')
    result=dict(passed=len(checks),database=Config.DB_NAME,records=15000,states=28,districts=138,checks=checks)
    (P/'DATASET_COVERAGE_TEST_RESULTS.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='checks'},indent=2))

if __name__=='__main__':main()
