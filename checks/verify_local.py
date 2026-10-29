from pathlib import Path
import sys,json
P=Path(__file__).resolve().parent
if P.name=='checks':P=P.parent
sys.path.insert(0,str(P))
from config import Config
from db import query_db
from app import app
from models.risk_engine import calculate_project_risk
from models.duplicate_engine import build_duplicate_lookup
checks=[]
def check(ok,label):
    assert ok,label
    checks.append(label);print('PASS',label,flush=True)
rows=query_db('SELECT * FROM road_projects ORDER BY work_id')
ml={r['work_id']:r for r in query_db('SELECT * FROM ml_analysis')}
risk={r['work_id']:r for r in query_db('SELECT * FROM risk_analysis')}
duplicates=build_duplicate_lookup(query_db('SELECT * FROM duplicate_analysis ORDER BY evidence_score DESC, pair_id ASC'))
check(len(rows)==len(ml)==len(risk)==15000,'Final application has 15000 source, financial and risk records')
check(all(len(json.loads(r['source_json']))==24 and r['latitude'] is None and r['longitude'] is None for r in rows),'Final application uses 24 source columns without coordinate data')
for r in rows:
    result=calculate_project_risk(r,ml[r['work_id']],[],duplicates.get(r['work_id'],[]))
    assert result['risk_score']==risk[r['work_id']]['risk_score'],r['work_id']
    assert all(0<=row['points']<=row['maximum_points'] for row in result['risk_breakdown'])
check(True,'Every final saved risk score matches its recalculated contributions')
app.config['TESTING']=True;c=app.test_client()
with c.session_transaction() as session:session['user']=dict(user_id=1,username='admin',full_name='Administrator',role='district_admin',district=None,mp_id=None,vendor_id=None)
check(len(c.get('/api/filters').get_json()['states'])==28,'Final application exposes all 28 states')
for work in ['R-00001','R-03837','R-05637']:
    detail=c.get('/api/projects/'+work).get_json()['data']
    report=c.get('/api/reports/project/'+work).get_json()['report']
    check(detail['risk_breakdown']['matches_stored_score'] and report['risk_breakdown']['matches_stored_score'],'Details/report score consistency: '+work)
    maxima={r['key']:r['maximum_points'] for r in detail['risk_breakdown']['components']}
    check(maxima['progress_gap']==10 and maxima['duplicate']==20,'Correct grading maxima: '+work)
check(c.get('/api/reports/project/R-00001/download').status_code==200,'Final report download works')
result=dict(passed=len(checks),checks=checks,database=Config.DB_NAME,records=15000,columns=24,states=28)
(P/'checks/LOCAL_VERIFICATION.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='checks'},indent=2))
