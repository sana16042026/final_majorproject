"""Fast, deterministic checks for workbook mapping and delay rules (no database)."""
import unittest
import json
import numpy as np
import pandas as pd
from services.data_processor import clean_and_normalize_data, load_and_validate_file, sanitize_record
from config import Config

class MasterDatasetTests(unittest.TestCase):
    def test_prediction_flags_do_not_treat_zero_as_overrun(self):
        from models.prediction_engine import _evaluate
        metrics,cutoff=_evaluate(np.array([0.,0.,20.,25.]),np.array([0.,0.,0.,16.]),15)
        self.assertEqual(cutoff,15)
        self.assertEqual(metrics['fp'],0)
        self.assertEqual(metrics['tp'],1)

    def test_master_mapping(self):
        raw,error=load_and_validate_file(Config.MASTER_DATASET)
        self.assertIsNone(error)
        frame=clean_and_normalize_data(raw,as_of='2026-10-28')
        self.assertEqual(len(frame),15000)
        first=frame.iloc[0]
        self.assertEqual(first.work_id,'R-00001')
        self.assertAlmostEqual(first.estimated_cost,5.81*10_000_000)
        self.assertEqual(first.length_m,1950)
        self.assertEqual(first.delay_days,29)
        self.assertEqual(first.physical_progress_pct,100)
        self.assertEqual(len(json.loads(first.source_json)),26)

    def test_delays_and_missing_dates(self):
        fixtures=[
            # completed late / early / unfinished overdue / not due / dates absent
            ('late','2025-01-01','2025-01-10','2025-01-15',100,5,'Completed'),
            ('early','2025-01-01','2025-01-10','2025-01-05',100,0,'Completed'),
            ('active','2025-01-01','2025-01-10','Not Completed',50,10,'Delayed'),
            ('notdue','2025-01-01','2025-02-10','Not Completed',50,0,'Ongoing'),
            ('missing','2025-01-01',None,None,50,None,'Ongoing'),
            ('nodate','2025-01-01','2025-01-10',None,100,None,'Completed'),
            ('invalid','2025-01-12','2025-01-10','2025-01-15',100,None,'Completed'),
        ]
        rows=[dict(work_id=k,start_date=s,expected_completion_date=e,completion_date=c,physical_progress_pct=p)
              for k,s,e,c,p,_,_ in fixtures]
        frame=clean_and_normalize_data(pd.DataFrame(rows),as_of='2025-01-20')
        for row,fixture in zip(frame.to_dict('records'),fixtures):
            value=fixture[5]
            if value is None:self.assertTrue(pd.isna(row['delay_days']),fixture[0])
            else:self.assertEqual(row['delay_days'],value,fixture[0])
            self.assertEqual(row['status'],fixture[6])
        self.assertIsNone(sanitize_record(frame.iloc[4].to_dict())['delay_days'])

    def test_refresh_date_updates_only_unfinished_delay(self):
        rows=pd.DataFrame([
            dict(work_id='done',completion_date='2025-01-15',expected_completion_date='2025-01-10',physical_progress_pct=100),
            dict(work_id='active',completion_date=None,expected_completion_date='2025-01-10',physical_progress_pct=50)])
        day1=clean_and_normalize_data(rows,as_of='2025-01-20')
        day2=clean_and_normalize_data(rows,as_of='2025-01-21')
        self.assertEqual(day1.delay_days.tolist(),[5,10])
        self.assertEqual(day2.delay_days.tolist(),[5,11])

    def test_missing_and_invalid_numeric_data(self):
        d=clean_and_normalize_data(pd.DataFrame([dict(work_id='a',length_km='bad',estimated_cost=np.inf,
            physical_progress_pct=130),dict(work_id='a'),dict(work_id='')]),as_of='2025-01-20')
        self.assertEqual(len(d),1)
        record=sanitize_record(d.iloc[0].to_dict())
        self.assertIsNone(record['estimated_cost'])
        self.assertIsNone(record['length_km'])
        self.assertIsNone(record['physical_progress_pct'])

    def test_financial_percentage_over_100_is_preserved(self):
        d=clean_and_normalize_data(pd.DataFrame([dict(work_id='overrun',physical_progress_pct=100,financial_progress_pct=116.89)]))
        self.assertEqual(d.iloc[0].financial_progress_pct,116.89)
        self.assertEqual(d.iloc[0].physical_financial_gap_pct,16.89)

if __name__=='__main__':unittest.main(verbosity=2)
