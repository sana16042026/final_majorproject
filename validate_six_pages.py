from pathlib import Path
import sys,json,re,subprocess,compileall
from html.parser import HTMLParser
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P))
from app import app
from db import query_db
checks=[]
def check(value,label):
    assert value,label
    checks.append(label);print('PASS',label,flush=True)
class Scan(HTMLParser):
    def __init__(self):super().__init__();self.ids=[];self.links=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag=='a':self.links.append(a.get('href'))
def login(client,role='district_admin',district=None):
    with client.session_transaction() as s:s['user']=dict(user_id=1,username='admin',full_name='Administrator',role=role,district=district,mp_id=None,vendor_id=None)
app.config['TESTING']=True
c=app.test_client();login(c)
navigation=['/','/projects','/upload','/financial-analysis','/similar-works','/risk-analysis']
for url in navigation+['/reports?work_id=R-00001']:
    r=c.get(url);check(r.status_code==200,'Page '+url)
    html=r.get_data(as_text=True);scan=Scan();scan.feed(html)
    check(len(scan.ids)==len(set(scan.ids)),'Unique DOM IDs '+url)
    sidebar=html.split('<ul class="sidebar-nav">')[1].split('</ul>')[0]
    ss=Scan();ss.feed(sidebar)
    check(ss.links==navigation,'Exactly six main navigation links '+url)
    for ix,script in enumerate(re.findall(r'<script>(.*?)</script>',html,re.S)):
        out=Path('six_page_script_checks')/(url.split('?')[0].strip('/').replace('/','_') or 'dashboard')/f'{ix}.js'
        out.parent.mkdir(parents=True,exist_ok=True);out.write_text(script,encoding='utf-8')
        subprocess.run(['node','--check',str(out)],check=True,capture_output=True)
    if url=='/risk-analysis':check('id="predictions-pane"' not in html and 'id="duplicates-pane"' not in html,'Risk dashboard only includes risk and alerts')
    if url=='/financial-analysis':check('id="predictions-pane"' not in html and 'id="duplicates-pane"' not in html,'Financial analysis shows anomalies without estimates')
    if url=='/similar-works':check('id="duplicates-pane"' in html and 'id="predictions-pane"' not in html,'Similarity groups wording and contextual evidence')
check('btn-modal-report' in c.get('/projects').get_data(as_text=True),'Report action in shared project Details')
db=query_db('SELECT COUNT(*) AS total,SUM(anomaly_detected=1) AS flagged,SUM(anomaly_detected=0) AS normal FROM ml_analysis',one=True)
for kind,key in [('anomalies','flagged'),('normal','normal'),('all','total')]:
    r=c.get('/api/financial-analysis/projects?kind='+kind);d=r.get_json()
    check(r.status_code==200 and d['total']==db[key],'Financial count '+kind)
    if kind!='all':check(all(x['anomaly_detected']==(kind=='anomalies') for x in d['projects']),'Correct model flags '+kind)
    check(d['summary']['analysed']==db['total'],'Live financial summary '+kind)
first=c.get('/api/financial-analysis/projects?kind=all&page=1').get_json()
second=c.get('/api/financial-analysis/projects?kind=all&page=2').get_json()
check(not ({x['work_id'] for x in first['projects']} & {x['work_id'] for x in second['projects']}),'Financial pagination')
check(c.get('/api/financial-analysis/projects?kind=all&search=R-00001').get_json()['total']==1,'Financial Work ID search')
check(c.get('/api/financial-analysis/projects?kind=bad').status_code==400,'Invalid filter rejected')
nlp_count=query_db('SELECT COUNT(*) AS n FROM nlp_analysis',one=True)['n']
d=c.get('/api/similarity/projects').get_json();check(d['total']==nlp_count,'Wording matches use current database')
if d['pairs']:
    key=d['pairs'][0]['work_id_1']
    found=c.get('/api/similarity/projects?search='+key).get_json()
    check(found['total']>0 and all(key in (p['work_id_1'],p['work_id_2']) for p in found['pairs']),'Similarity search')
for path in ['/api/duplicates/summary','/api/duplicates/projects','/api/risk-analysis','/api/risk-analysis/projects?level=MEDIUM','/api/alerts','/api/reports/project/R-00001','/api/reports/project/R-00001/download']:
    check(c.get(path).status_code==200,'Preserved endpoint '+path)
login(c,district='Pune')
for path,key in [('/api/financial-analysis/projects?kind=all','projects'),('/api/similarity/projects','pairs')]:
    rows=c.get(path).get_json()[key]
    check(all((x['district']=='Pune') if key=='projects' else (x['district_1']==x['district_2']=='Pune') for x in rows),'District scope '+key)
for role in ['auditor','ministry']:
    login(c,role)
    check(c.get('/financial-analysis').status_code==200 and c.get('/similar-works').status_code==200,'Analysis role access '+role)
for role in ['citizen','vendor']:
    login(c,role)
    check(c.get('/financial-analysis').status_code==302 and c.get('/similar-works').status_code==302,'Restricted analysis pages '+role)
    check(c.get('/api/financial-analysis/projects').status_code==403 and c.get('/api/similarity/projects').status_code==403,'Restricted analysis APIs '+role)
anon=app.test_client();check(anon.get('/api/financial-analysis/projects').status_code==401,'Anonymous API blocked')
for file in (P/'static/js').glob('*.js'):subprocess.run(['node','--check',str(file)],check=True,capture_output=True)
check(compileall.compile_dir(str(P),quiet=1),'Python compilation and all JavaScript syntax checks')
result=dict(passed=len(checks),checks=checks,financial_counts=db,wording_pairs=nlp_count,notes='Read-only integration against current MySQL data; no models were retrained or records changed.')
Path('SIX_PAGE_TEST_RESULTS.json').write_text(json.dumps(result,indent=2,default=str),encoding='utf-8')
print(json.dumps(result,indent=2,default=str),flush=True)
