from pathlib import Path
import os,sys,json
P=Path(__file__).resolve().parent
if P.name=='checks':P=P.parent
sys.path.insert(0,str(P))
os.environ['DB_NAME']='drishti_final_major_validation'
from app import app
from db import query_db
from services.duplicate_evidence import explain_duplicate_evidence
checks=[]
def check(ok,label):
    assert ok,label
    checks.append(label);print('PASS',label,flush=True)
app.config['TESTING']=True
projects={p['work_id']:p for p in query_db('SELECT * FROM road_projects')}
pairs=query_db('SELECT * FROM duplicate_analysis ORDER BY evidence_score DESC,pair_id ASC')
for p in pairs:
    d=explain_duplicate_evidence(p,projects[p['work_id_1']],projects[p['work_id_2']])
    assert d['total']==p['evidence_score'],p['pair_id']
    assert len(d['components'])==6 and sum(r['maximum'] for r in d['components'])==100
    assert all(0<=r['points']<=r['maximum'] for r in d['components'])
check(len(pairs)==20000,'All 20000 saved pairs reconcile exactly with six evidence components')
c=app.test_client();c.post('/login',data=dict(username='admin',password='admin123'))
listing=c.get('/api/duplicates/projects').get_json()
check(all('pair_id' in p for p in listing['pairs']),'Pair listing supplies IDs for clickable evidence buttons')
for classification in ['Likely duplicate','Possible overlap']:
    pair=next(p for p in pairs if p['classification']==classification)
    r=c.get(f"/api/duplicates/{pair['pair_id']}/evidence")
    check(r.status_code==200 and r.get_json()['total']==pair['evidence_score'],'Evidence API matches saved '+classification+' score')
page=c.get('/similar-works').get_data(as_text=True)
check('duplicate_evidence.js' in page and 'data-evidence-pair' in page,'Page loads explanation handler and renders score buttons')
check(c.get('/api/duplicates/999999999/evidence').status_code==404,'Unknown pair returns not found')
guest=app.test_client();check(guest.get(f"/api/duplicates/{pairs[0]['pair_id']}/evidence").status_code==401,'Anonymous evidence access blocked')
citizen=app.test_client();citizen.post('/login',data=dict(username='citizen',password='citizen123'))
check(citizen.get(f"/api/duplicates/{pairs[0]['pair_id']}/evidence").status_code==403,'Citizen cannot access restricted evidence')
scoped=app.test_client();scoped.post('/login',data=dict(username='admin_pune',password='pune123'))
pair=next(p for p in pairs if projects[p['work_id_1']]['district']!='Pune')
check(scoped.get(f"/api/duplicates/{pair['pair_id']}/evidence").status_code==404,'Out-of-district pair cannot leak evidence to scoped administrator')
# Explicit zero-point and rounding cases independently exercise the explanation.
sample=dict(pair_id=1,work_id_1='A',work_id_2='B',evidence_score=55.1,text_similarity=.502,
            classification='Possible overlap',evidence='same constituency; length within 1%; estimated cost within 1%')
project=dict(description='Example',district='District',state='State',constituency='C',road_type='Road',length_m=100,estimated_cost=100)
d=explain_duplicate_evidence(sample,project,project)
check(d['total']==55.1 and d['components'][1]['points']==0 and d['components'][3]['points']==0,'Zero-point factors and saved rounding are shown explicitly')
out=dict(passed=len(checks),checks=checks,pairs_reconciled=len(pairs),database='drishti_final_major_validation')
(P/'checks/EVIDENCE_TEST_RESULTS.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in out.items() if k!='checks'},indent=2))
