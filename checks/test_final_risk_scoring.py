"""Focused audit of every risk factor, threshold, maximum and total."""
import unittest
from models.risk_engine import calculate_project_risk

BASE=dict(work_id='audit',cost_overrun_pct=0,actual_expenditure=90,sanctioned_amount=100,estimated_cost=100,delay_days=0,physical_progress_pct=100,financial_progress_pct=100,physical_financial_gap_pct=0,number_of_bidders=None)
MAXIMA={'financial_anomaly':25,'cost_overrun':25,'delay':25,'progress_gap':10,'duplicate':20,'bidders':10,'expenditure_ratio':15}
def calc(changes=None,ml=None,duplicates=None,nlp=None):
    return calculate_project_risk(dict(BASE,**(changes or {})),ml or dict(anomaly_detected=0,anomaly_score=.2),nlp or [],[] if duplicates is None else duplicates)
def factor(result,key):return next(r for r in result['risk_breakdown'] if r['key']==key)
def match(kind):return dict(classification=kind,other_work_id='R-12666',evidence_score=75,evidence='same district and contextual evidence')

class FinalRiskTests(unittest.TestCase):
    def audit(self,result):
        self.assertEqual({r['key']:r['maximum_points'] for r in result['risk_breakdown']},MAXIMA)
        self.assertEqual(sum(r['points'] for r in result['risk_breakdown']),result['uncapped_score'])
        self.assertEqual(result['risk_score'],min(100,result['uncapped_score']))
        for row in result['risk_breakdown']:self.assertTrue(0<=row['points']<=row['maximum_points'])
    def test_all_maxima_and_zeroes(self):
        r=calc();self.audit(r);self.assertEqual(r['risk_score'],0)
    def test_cost_overrun_boundaries(self):
        for value,points in [(5,0),(5.01,8),(15,8),(15.01,15),(30,15),(30.01,25)]:
            with self.subTest(value=value):
                r=calc({'cost_overrun_pct':value});self.audit(r);self.assertEqual(factor(r,'cost_overrun')['points'],points)
    def test_delay_boundaries(self):
        for value,points in [(20,0),(21,8),(60,8),(61,15),(120,15),(121,25)]:
            with self.subTest(value=value):
                r=calc({'delay_days':value});self.audit(r);self.assertEqual(factor(r,'delay')['points'],points)
    def test_progress_gap_boundaries(self):
        for value,points in [(-2.33,0),(0,0),(5,0),(5.01,2.5),(15,2.5),(15.01,6),(25,6),(25.01,10)]:
            with self.subTest(value=value):
                r=calc({'physical_financial_gap_pct':value});self.audit(r);self.assertEqual(factor(r,'progress_gap')['points'],points)
    def test_missing_progress_does_not_award_points(self):
        for changes in [dict(physical_financial_gap_pct=None,physical_progress_pct=None,financial_progress_pct=90),dict(physical_financial_gap_pct=None,financial_progress_pct=None,physical_progress_pct=0)]:
            r=calc(changes);self.audit(r);self.assertEqual(factor(r,'progress_gap')['points'],0);self.assertEqual(factor(r,'progress_gap')['status'],'Unavailable')
    def test_gap_fallback_and_explicit_zero(self):
        r=calc(dict(physical_financial_gap_pct=None,physical_progress_pct=30,financial_progress_pct=60));self.assertEqual(factor(r,'progress_gap')['points'],10)
        r=calc(dict(physical_financial_gap_pct=0,physical_progress_pct=30,financial_progress_pct=60));self.assertEqual(factor(r,'progress_gap')['points'],0)
    def test_duplicate_awards(self):
        for kind,points in [('Likely duplicate',20),('Possible overlap',10)]:
            r=calc(duplicates=[match(kind)]);self.audit(r);self.assertEqual(factor(r,'duplicate')['points'],points)
    def test_wording_fallback_only_without_context(self):
        nlp=[dict(matched_work_id='R-00002',similarity_pct=90)]
        r=calculate_project_risk(BASE,dict(anomaly_detected=0),nlp,None);self.audit(r);self.assertEqual(factor(r,'duplicate')['points'],20)
        r=calculate_project_risk(BASE,dict(anomaly_detected=0),nlp,[]);self.assertEqual(factor(r,'duplicate')['points'],0)
    def test_bidders(self):
        for value,points in [(None,0),(0,0),(1,10),(2,0)]:
            r=calc({'number_of_bidders':value});self.audit(r);self.assertEqual(factor(r,'bidders')['points'],points)
    def test_expenditure_threshold(self):
        for actual,points in [(179.99,0),(180,15)]:
            r=calc({'actual_expenditure':actual,'sanctioned_amount':200});self.audit(r);self.assertEqual(factor(r,'expenditure_ratio')['points'],points)
    def test_ml_flag(self):
        r=calc(ml=dict(anomaly_detected=1,anomaly_score=.9));self.audit(r);self.assertEqual(factor(r,'financial_anomaly')['points'],25)
    def test_cap_and_categories(self):
        r=calc(dict(cost_overrun_pct=31,delay_days=121,physical_financial_gap_pct=26,number_of_bidders=1,actual_expenditure=200),dict(anomaly_detected=1),[match('Likely duplicate')]);self.audit(r)
        self.assertEqual((r['uncapped_score'],r['risk_score'],r['cap_adjustment'],r['risk_level']),(130,100,-30,'HIGH'))
        self.assertEqual(calc(dict(cost_overrun_pct=31,delay_days=61))['risk_level'],'MEDIUM')
        self.assertEqual(calc(dict(cost_overrun_pct=31,delay_days=121),dict(anomaly_detected=1))['risk_level'],'HIGH')
        self.assertEqual(calc()['risk_level'],'LOW')
    def test_contextual_evidence_threshold_matches_displayed_precision(self):
        from models.duplicate_engine import run_duplicate_analysis
        records=[]
        for i in range(30):
            pair=i<2
            records.append(dict(work_id=f'W-{i:02}',description='Road repair near Maple' if pair else f'Road repair near Place{i}',
                state='State',district='PairDistrict' if pair else f'District{i}',
                constituency='Same' if pair else str(i),road_type='Rural',
                length_m=1000 if i==0 else 3000+i*100,estimated_cost=100 if i==0 else 500+i*100))
        pairs,_=run_duplicate_analysis(records)
        match=next(p for p in pairs if {p['work_id_1'],p['work_id_2']}=={'W-00','W-01'})
        self.assertEqual(match['evidence_score'],80)
        self.assertEqual(match['classification'],'Likely duplicate')
    def test_screenshot_example_is_18(self):
        r=calc(dict(delay_days=29,physical_financial_gap_pct=-2.33),duplicates=[match('Possible overlap')]);self.audit(r)
        self.assertEqual(r['risk_score'],18)
        self.assertEqual((factor(r,'progress_gap')['points'],factor(r,'progress_gap')['maximum_points']),(0,10))
        self.assertEqual((factor(r,'duplicate')['points'],factor(r,'duplicate')['maximum_points']),(10,20))

if __name__=='__main__':unittest.main(verbosity=2)
