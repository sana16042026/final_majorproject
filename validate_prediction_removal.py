from pathlib import Path
import sys,json,re
from html.parser import HTMLParser
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P))
from app import app
from db import query_db
checks=[]
def check(v,label):assert v,label;checks.append(label);print('PASS',label,flush=True)
app.config['TESTING']=True;c=app.test_client()
with c.session_transaction() as s:s['user']=dict(user_id=1,username='admin',full_name='Administrator',role='district_admin',district=None,mp_id=None,vendor_id=None)
class DivCheck(HTMLParser):
    def __init__(self):super().__init__();self.depth=0;self.minimum=0
    def handle_starttag(self,t,a):
        if t=='div':self.depth+=1
    def handle_endtag(self,t):
        if t=='div':self.depth-=1;self.minimum=min(self.minimum,self.depth)
for url in ['/','/projects','/upload','/financial-analysis','/similar-works','/risk-analysis','/reports?work_id=R-05637']:
    r=c.get(url);check(r.status_code==200,'Page renders '+url)
    html=r.get_data(as_text=True);parser=DivCheck();parser.feed(html)
    check(parser.depth==0 and parser.minimum>=0,'Balanced page containers '+url)
    check('predictions-tab' not in html and 'predictions-pane' not in html and 'summary-likely-delayed' not in html,'No estimation controls '+url)
for url,method in [('/api/predictions/summary','get'),('/api/predictions/projects','get'),('/api/run-prediction','post')]:check(getattr(c,method)(url).status_code==404,'Retired route '+url)
for url,key in [('/api/projects/R-05637','data'),('/api/reports/project/R-05637','report')]:
    d=c.get(url).get_json()[key]
    check('prediction' not in d and d['project']['delay_days']==0 and d['project']['cost_overrun_pct']==0,'Recorded values retained without model estimate '+url)
    check(d['risk_breakdown']['calculated_score']==d['risk_breakdown']['stored_score'],'Clickable risk score retained '+url)
r=c.get('/api/reports/project/R-05637/download')
check(r.status_code==200 and b'predicted_delay_days' not in r.data and b'predicted_overrun_pct' not in r.data,'Downloaded report excludes estimates')
s=c.get('/api/reports/summary').get_json()['summary'];check('likely_delayed' not in s and 'likely_overrun' not in s,'Summary excludes estimate counts')
check(not (P/'models/prediction_engine.py').exists() and not (P/'services/prediction_service.py').exists(),'Estimator source modules removed')
check(query_db('SELECT COUNT(*) AS n FROM road_projects',one=True)['n']==15000,'Application dataset still contains 15000 works')
result=dict(passed=len(checks),checks=checks,notes='Read-only checks against the current application database. Legacy estimator tables were not modified.')
Path('PREDICTION_REMOVAL_CHECKS.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2),flush=True)
