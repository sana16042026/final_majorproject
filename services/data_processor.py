"""Master road workbook mapping, date-derived delays, and atomic analysis refresh."""
import json
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from db import get_db_connection, query_db
from models.nlp_engine import run_nlp_similarity_analysis
from models.ml_engine import run_ml_anomaly_detection
from models.risk_engine import run_risk_analysis_for_all
from models.duplicate_engine import run_duplicate_analysis, build_duplicate_lookup

CRORE=10_000_000
ALIASES = {
    'work_description':'description', 'vendor_name':'vendor_id', 'elected_mp':'mp_id',
    'road_length_km':'length_km', 'estimated_cost_inr_crore':'estimated_cost',
    'sanctioned_amount_inr_crore':'sanctioned_amount',
    'expenditure_amount_inr_crore':'actual_expenditure', 'cost_per_km_inr_crore':'cost_per_km',
    'progress_percentage':'physical_progress_pct', 'financial_percentage':'financial_progress_pct',
    'implementing_agency_ida':'implementing_agency'
}
MONEY_SOURCE = {'estimated_cost_inr_crore','sanctioned_amount_inr_crore','expenditure_amount_inr_crore','cost_per_km_inr_crore'}
TEXT_FIELDS=['work_id','work_title','description','work_type','road_type','state','district','constituency',
             'house','mp_id','implementing_agency','vendor_id','payment_status','progress_basis']
NUMBER_FIELDS=['length_m','length_km','cost_per_km','estimated_cost','sanctioned_amount','actual_expenditure',
    'tender_amount','agreement_amount','final_amount','cost_overrun_pct','delay_days','number_of_bidders',
    'physical_progress_pct','financial_progress_pct','physical_financial_gap_pct','latitude','longitude','invested_amount_inr']
DATE_FIELDS=['start_date','expected_completion_date','completion_date','analysis_as_of']
ROAD_PROJECT_FIELDS=TEXT_FIELDS+NUMBER_FIELDS+DATE_FIELDS+['status','delay_basis','source_json']
REQUIRED_COLUMNS=['work_id','description','estimated_cost','sanctioned_amount','actual_expenditure','length_km','physical_progress_pct','financial_progress_pct']

def reporting_date():
    return datetime.now(ZoneInfo('Asia/Kolkata')).date()

def clean_place_name(series, default=''):
    s=series.fillna(default).astype(str).str.replace(r'^\s*\d+\s*[.)\-:]*\s*','',regex=True)
    return s.str.replace(r'\s+',' ',regex=True).str.strip()

def load_and_validate_file(file_path):
    ext=os.path.splitext(str(file_path))[1].lower()
    try:
        if ext=='.csv': df=pd.read_csv(file_path,low_memory=False)
        elif ext in {'.xlsx','.xls'}: df=pd.read_excel(file_path)
        else: return None,'Use an Excel workbook (.xlsx) or CSV file.'
        if df.empty: return None,'The dataset has no records.'
        source=df.astype(object).where(pd.notna(df),None).apply(lambda row: json.dumps(row.to_dict(),default=str,allow_nan=False),axis=1)
        df.columns=[str(c).strip().lower().replace(' ','_').replace('-','_') for c in df.columns]
        if df.columns.duplicated().any(): return None,'Dataset has ambiguous duplicate column names.'
        for col in MONEY_SOURCE & set(df.columns):
            df[col]=pd.to_numeric(df[col],errors='coerce')*CRORE
        df=df.rename(columns=ALIASES)
        if df.columns.duplicated().any(): return None,'Dataset contains two columns for the same mapped field.'
        if 'length_km' not in df and 'length_m' in df:
            df['length_km']=pd.to_numeric(df['length_m'],errors='coerce')/1000
        missing=[c for c in REQUIRED_COLUMNS if c not in df]
        if missing: return None,'Missing required source fields: '+', '.join(missing)
        df['source_json']=source
        return df,None
    except Exception as exc:
        return None,'Could not read dataset: '+str(exc)

def clean_and_normalize_data(df, as_of=None):
    d=df.copy()
    d=d.dropna(subset=['work_id'])
    d['work_id']=d['work_id'].astype(str).str.strip()
    d=d.loc[~d.work_id.str.lower().isin(['','nan','none'])].drop_duplicates('work_id',keep='first').reset_index(drop=True)
    for col in TEXT_FIELDS:
        d[col]=d.get(col,pd.Series('',index=d.index)).fillna('').astype(str).str.strip()
    for col in ['state','district']: d[col]=clean_place_name(d[col])
    # House is inferred only from the explicit constituency prefix when available.
    house=d['constituency'].str.extract(r'^(Lok Sabha|Rajya Sabha)',expand=False).fillna('')
    d['house']=d['house'].where(d['house']!='',house)
    for col in NUMBER_FIELDS:
        d[col]=pd.to_numeric(d.get(col,pd.Series(np.nan,index=d.index)),errors='coerce').replace([np.inf,-np.inf],np.nan)
    for col in ['length_m','length_km','estimated_cost','sanctioned_amount','actual_expenditure','cost_per_km']:
        d[col]=d[col].where(d[col]>=0)
    d['physical_progress_pct']=d['physical_progress_pct'].where(d['physical_progress_pct'].between(0,100))
    # Financial drawdown can legitimately exceed 100% of sanction (overrun).
    d['financial_progress_pct']=d['financial_progress_pct'].where(d['financial_progress_pct']>=0)
    d['length_km']=d['length_km'].fillna(d['length_m']/1000)
    d['length_m']=d['length_m'].fillna(d['length_km']*1000)
    d['cost_per_km']=d['cost_per_km'].fillna(d['estimated_cost']/d['length_km'].where(d['length_km']>0))
    d['cost_overrun_pct']=(100*(d['actual_expenditure']/d['sanctioned_amount'].where(d['sanctioned_amount']>0)-1)).clip(lower=0).round(2)
    d['physical_financial_gap_pct']=(d['financial_progress_pct']-d['physical_progress_pct']).round(2)
    for col in ['start_date','expected_completion_date','completion_date']:
        # 'Not Completed', '-', invalid dates become missing, never fake completion dates.
        d[col]=pd.to_datetime(d.get(col,pd.Series(pd.NaT,index=d.index)),errors='coerce',format='mixed').dt.normalize()
    today=pd.Timestamp(as_of or reporting_date()).normalize()
    completed=d['completion_date'].notna() | (d['physical_progress_pct']>=100)
    expected=d['expected_completion_date']
    valid_expected=expected.notna() & (d['start_date'].isna() | (expected>=d['start_date']))
    completed_valid=d['completion_date'].notna() & (d['start_date'].isna() | (d['completion_date']>=d['start_date']))
    end=d['completion_date'].where(completed,today)
    usable=valid_expected & (~completed | completed_valid)
    d['delay_days']=(end-expected).dt.days.clip(lower=0).where(usable)
    d['delay_basis']=np.select([completed & usable,~completed & usable],
        ['Actual completion date minus expected completion date','Reporting date minus expected completion date'],default='Unavailable: missing or inconsistent dates')
    delayed=~completed & (d['delay_days']>0)
    known=d['start_date'].notna() | d['physical_progress_pct'].notna() | expected.notna()
    d['status']=np.select([completed,delayed,known],['Completed','Delayed','Ongoing'],default='Unavailable')
    d['analysis_as_of']=today
    if 'source_json' not in d: d['source_json']='{}'
    return d

def sanitize_record(row):
    result={}
    for key in ROAD_PROJECT_FIELDS:
        value=row.get(key)
        if value is None or pd.isna(value): result[key]=None
        elif key in DATE_FIELDS: result[key]=pd.Timestamp(value).strftime('%Y-%m-%d')
        elif key in {'delay_days','number_of_bidders'}: result[key]=int(value)
        elif isinstance(value,(np.integer,)): result[key]=int(value)
        elif isinstance(value,(float,np.floating)): result[key]=float(value) if np.isfinite(value) else None
        else: result[key]=value
    return result

def _insert(cursor,table,records,fields):
    if not records: return
    sql='INSERT INTO `'+table+'` ('+','.join('`'+f+'`' for f in fields)+') VALUES ('+','.join('%('+f+')s' for f in fields)+')'
    # Analysis dictionaries may contain UI explanation metadata. Only schema
    # fields are bound to SQL, so nested evidence is never sent as a SQL value.
    for start in range(0,len(records),1000):
        batch=[{field:record[field] for field in fields} for record in records[start:start+1000]]
        cursor.executemany(sql,batch)

def process_and_save_dataset(file_path):
    frame,error=load_and_validate_file(file_path)
    if error: return {'success':False,'message':error}
    return analyze_and_save(clean_and_normalize_data(frame))

def reprocess_current_dataset():
    frame=pd.DataFrame(query_db('SELECT * FROM road_projects ORDER BY work_id'))
    if frame.empty: return {'success':False,'message':'Load the master workbook first.'}
    return analyze_and_save(clean_and_normalize_data(frame))

def analyze_and_save(frame):
    if frame.empty: return {'success':False,'message':'No valid Work IDs were found.'}
    projects=[sanitize_record(r) for r in frame.to_dict('records')]
    similarity,nlp_lookup=run_nlp_similarity_analysis(projects,threshold=.70)
    ml,ml_lookup=run_ml_anomaly_detection(frame,contamination=.15)
    duplicates,dup_summary=run_duplicate_analysis(projects)
    risk,_=run_risk_analysis_for_all(projects,ml_lookup,nlp_lookup,build_duplicate_lookup(duplicates))
    conn=get_db_connection()
    try:
        conn.begin()
        with conn.cursor() as cursor:
            for table in ['duplicate_analysis','duplicate_summary','risk_analysis','nlp_analysis','ml_analysis','road_projects']:
                cursor.execute('DELETE FROM `'+table+'`')
            _insert(cursor,'road_projects',projects,ROAD_PROJECT_FIELDS)
            _insert(cursor,'ml_analysis',ml,['work_id','anomaly_score','anomaly_detected','model_name'])
            _insert(cursor,'nlp_analysis',similarity,['work_id_1','work_id_2','similarity_score','similarity_status'])
            _insert(cursor,'risk_analysis',risk,['work_id','risk_score','risk_level','risk_reason'])
            _insert(cursor,'duplicate_analysis',duplicates,['work_id_1','work_id_2','text_similarity','evidence_score','classification','evidence'])
            cursor.execute('INSERT INTO duplicate_summary (metrics_json) VALUES (%s)',(json.dumps(dup_summary,allow_nan=False),))
            cursor.execute("SELECT vendor_id FROM road_projects WHERE vendor_id<>'' GROUP BY vendor_id ORDER BY COUNT(*) DESC LIMIT 1")
            top=cursor.fetchone()
            if top: cursor.execute("UPDATE users SET vendor_id=%s WHERE username='vendor'",(top['vendor_id'],))
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return {'success':False,'message':'Database refresh rolled back: '+str(exc)}
    finally: conn.close()
    return {'success':True,'message':f'Master dataset processed: {len(projects):,} projects; all analyses refreshed.',
        'total_projects':len(projects),'ml_anomalies_detected':sum(r['anomaly_detected'] for r in ml),
        'similar_descriptions_found':len(similarity),'high_risk_projects':sum(r['risk_level']=='HIGH' for r in risk),
        'location_duplicate_pairs':len(duplicates),'likely_duplicates':dup_summary.get('likely_duplicates',0),
        'analysis_as_of':str(frame['analysis_as_of'].iloc[0].date()),'money_unit':'INR',
        'delay_days_available':int(frame['delay_days'].notna().sum())}


def refresh_saved_risk_scores():
    """Apply current scoring rules without replacing projects or other analyses."""
    from models.risk_engine import run_risk_analysis_for_all
    projects=query_db('SELECT * FROM road_projects ORDER BY work_id')
    ml={r['work_id']:r for r in query_db('SELECT * FROM ml_analysis')}
    nlp={}
    for row in query_db('SELECT * FROM nlp_analysis ORDER BY similarity_score DESC'):
        for me,other in ((row['work_id_1'],row['work_id_2']),(row['work_id_2'],row['work_id_1'])):
            nlp.setdefault(me,[]).append(dict(matched_work_id=other,similarity_pct=row['similarity_score']*100))
    duplicates=build_duplicate_lookup(query_db('SELECT * FROM duplicate_analysis ORDER BY evidence_score DESC, pair_id ASC'))
    risks,_=run_risk_analysis_for_all(projects,ml,nlp,duplicates)
    conn=get_db_connection()
    try:
        conn.begin()
        with conn.cursor() as cursor:
            cursor.executemany('UPDATE risk_analysis SET risk_score=%(risk_score)s,risk_level=%(risk_level)s,risk_reason=%(risk_reason)s WHERE work_id=%(work_id)s',
                [{k:r[k] for k in ('work_id','risk_score','risk_level','risk_reason')} for r in risks])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return len(risks)
