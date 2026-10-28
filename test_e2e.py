"""Real-MySQL integration tests. Uses only its own dedicated validation schema."""
import os
os.environ['DB_NAME']='drishti_master_validation_v3'
import compileall
import json
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from config import Config
from init_db import init_database
from db import query_db
from services.data_processor import reprocess_current_dataset
from app import app

checks=[]
def check(value,label):
    assert value,label
    checks.append(label)
    print('PASS:',label,flush=True)

def main():
    init_database();init_database()
    app.config['TESTING']=True
    client=app.test_client()
    check(client.get('/api/dashboard').status_code==401,'Anonymous API requires login')
    check(client.post('/login',data={'username':'admin','password':'admin123'}).status_code==302,'Administrator login')
    for path in ['/','/projects','/upload','/risk-analysis','/reports']:
        check(client.get(path).status_code==200,'Page '+path)
    # Test real multipart Excel upload through the Flask route into MySQL.
    with open(Config.MASTER_DATASET,'rb') as stream:
        response=client.post('/api/upload',data={'file':(stream,'Master_Road_Work_Dataset_15000.xlsx')},content_type='multipart/form-data')
    print('UPLOAD RESULT',response.status_code,response.get_json(),flush=True)
    check(response.status_code==200 and response.get_json()['success'],'Full Excel upload and all analysis modules')
    project_rows=query_db('SELECT * FROM road_projects ORDER BY work_id')
    check(len(project_rows)==15000 and len({r['work_id'] for r in project_rows})==15000,'15000 unique records persisted')
    raw=pd.read_excel(Config.MASTER_DATASET)
    expected=pd.to_datetime(raw.Expected_Completion_Date,errors='coerce',format='mixed')
    completion=pd.to_datetime(raw.Completion_Date,errors='coerce',format='mixed')
    as_of=pd.Timestamp(response.get_json()['analysis_as_of'])
    end=completion.where(completion.notna(),as_of)
    delays=(end-expected).dt.days.clip(lower=0)
    stored={r['work_id']:r for r in project_rows}
    check(all(stored[k]['delay_days']==int(v) for k,v in zip(raw.Work_ID,delays)),'All 15000 delays agree with independent date calculation')
    check(abs(stored['R-00001']['actual_expenditure']-5.46*10_000_000)<.01,'Crore source values converted to rupees correctly')
    check(all(len(json.loads(r['source_json']))==26 for r in project_rows),'Every original workbook field preserved')
    check(stored['R-09262']['financial_progress_pct']==116.89 and stored['R-09262']['physical_financial_gap_pct']==16.89,'Financial progress over 100 percent retained as valid overrun evidence')
    counts={t:query_db('SELECT COUNT(*) n FROM '+t,one=True)['n'] for t in ['road_projects','ml_analysis','risk_analysis','nlp_analysis','duplicate_analysis','predictions']}
    check(counts['ml_analysis']==counts['risk_analysis']==counts['predictions']==15000,'Financial, risk and prediction results persisted for each work')
    check(counts['nlp_analysis']>0 and counts['duplicate_analysis']>0,'Both text similarity and contextual duplicates executed')
    predicted=query_db('SELECT * FROM predictions')
    check(all(r['delay_likely']==int(r['predicted_delay_days']>30) and r['overrun_likely']==int(r['predicted_overrun_pct']>15) for r in predicted),'Prediction flags use documented day and overrun thresholds')
    ml=query_db('SELECT * FROM ml_analysis')
    check(len({r['anomaly_score'] for r in ml})>1,'Financial scores have real variation')
    dashboard=client.get('/api/dashboard').get_json()
    check(dashboard['cards']['total_projects']==15000,'Dashboard total equals database')
    for key,status in [('completed_projects','Completed'),('ongoing_projects','Ongoing'),('delayed_projects','Delayed')]:
        check(dashboard['cards'][key]==sum(r['status']==status for r in project_rows),'Dashboard status count '+status)
    check(sum(dashboard['charts']['risk_chart']['data'])==15000,'Risk chart includes current database records')
    projects=client.get('/api/projects?search=R-00001').get_json()
    check(projects['total']==1 and projects['projects'][0]['delay_days']==29,'Searchable project table shows correct delay')
    for path in ['/api/filters','/api/risk-analysis','/api/risk-analysis/projects?level=HIGH','/api/predictions/summary',
                 '/api/predictions/projects?kind=all','/api/duplicates/summary','/api/duplicates/projects?kind=all',
                 '/api/alerts','/api/projects/R-00001','/api/reports/project/R-00001','/api/reports/summary']:
        r=client.get(path)
        check(r.status_code==200,'API '+path)
    details=client.get('/api/projects/R-00001').get_json()['data']['project']
    check(details['delay_days']==29 and details['delay_basis'].startswith('Actual'),'Project details expose delay calculation basis')
    report=client.get('/api/reports/project/R-00001').get_json()['report']['project']
    check(report['delay_days']==29,'Report matches persisted delay')
    check(client.get('/api/reports/project/R-00001/download').status_code==200,'Downloadable project report')
    file=client.get('/api/sample/download-template')
    check(file.status_code==200 and file.data==Path(Config.MASTER_DATASET).read_bytes(),'Master workbook download matches source')
    # Simulate a failure after deletes; the previously published snapshot must survive.
    # Storage rollback is independent of model fitting; stub detector outputs only
    # in this intentionally failing transaction so it doesn't refit every model.
    with patch('services.data_processor._insert',side_effect=RuntimeError('Simulated storage failure')), \
         patch('services.data_processor.run_nlp_similarity_analysis',return_value=([],{})), \
         patch('services.data_processor.run_ml_anomaly_detection',return_value=([],{})), \
         patch('services.data_processor.run_duplicate_analysis',return_value=([],{})), \
         patch('services.data_processor.run_prediction_analysis',return_value=([],{})):
        failed=reprocess_current_dataset()
    check(not failed['success'] and query_db('SELECT COUNT(*) n FROM road_projects',one=True)['n']==15000,'Failed refresh rolls back without losing published data')
    # The rerun endpoint recalculates delays and every dependent result together.
    refreshed=client.post('/api/run-ml')
    check(refreshed.status_code==200 and refreshed.get_json()['success'],'Rerun endpoint refreshes the complete pipeline')
    after={t:query_db('SELECT COUNT(*) n FROM '+t,one=True)['n'] for t in counts}
    check(after==counts,'Repeat processing does not duplicate or retain stale analysis records')
    client.get('/logout');client.post('/login',data={'username':'citizen','password':'citizen123'})
    public=client.get('/api/projects/R-00001').get_json()['data']['project']
    check('source_json' not in public and 'vendor_id' not in public,'Original source JSON does not bypass citizen field restrictions')
    check(client.post('/api/run-ml').status_code==403 and client.get('/api/reports/summary').status_code==403,'Citizen cannot modify analysis or view restricted reports')
    check(compileall.compile_dir(str(Path(__file__).parent),quiet=1),'All Python files compile')
    result={'passed':len(checks),'checks':checks,'database':Config.DB_NAME,'analysis_as_of':str(as_of.date()),
        'table_counts':counts,'status_counts':{s:sum(r['status']==s for r in project_rows) for s in ['Completed','Ongoing','Delayed']},
        'delay_min':int(delays.min()),'delay_max':int(delays.max()),
        'limitations':['Existing models are retained; source Progress_Basis includes synthetic values, so model metrics are not real-world fraud validation.',
            'Unfinished-work delay is observed overdue time as of the reporting date, not final completion delay.',
            'Contextual duplicate candidates remain capped at 20000; wording matches at 1000.']}
    Path('TEST_RESULTS.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()
