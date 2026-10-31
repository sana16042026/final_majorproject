"""Integration checks for browser-created accounts against a validation database."""
from pathlib import Path
import os,sys,re,uuid,json
P=Path(__file__).resolve().parent
if P.name=='checks':P=P.parent
sys.path.insert(0,str(P))
os.environ['DB_NAME']='drishti_final_major_validation'
from app import app
from db import query_db,execute_db
from werkzeug.security import check_password_hash

prefix='webtest_'+uuid.uuid4().hex[:10]
password='DemoSecure123!'
checks=[]
def check(ok,label):
    assert ok,label
    checks.append(label);print('PASS',label,flush=True)
def token(client,path):
    r=client.get(path)
    assert r.status_code==200,(path,r.status_code)
    match=re.search(r'name="csrf_token" value="([^"]+)"',r.get_data(as_text=True))
    assert match
    return match.group(1)
def payload(name,**changes):
    return dict(username=prefix+name,full_name='Example Person',password=password,confirm_password=password,**changes)
def login(client,name,pwd=password):return client.post('/login',data=dict(username=name,password=pwd))

def main():
    app.config['TESTING']=True
    c=app.test_client()
    try:
        check('Sign Up' in c.get('/login').get_data(as_text=True),'Login screen links to Sign Up')
        check(c.post('/signup',data=payload('_blocked')).status_code==400,'Signup rejects missing CSRF token')
        csrf=token(c,'/signup')
        bad=payload('_short');bad.update(password='short',confirm_password='short',csrf_token=csrf)
        check(c.post('/signup',data=bad).status_code==400,'Short password rejected')
        bad=payload('_mismatch');bad.update(confirm_password='different',csrf_token=csrf)
        check(c.post('/signup',data=bad).status_code==400,'Password confirmation checked')
        bad=payload('_bad');bad.update(username='bad username!',csrf_token=csrf)
        check(c.post('/signup',data=bad).status_code==400,'Invalid username rejected')
        data=payload('_public',role='district_admin',scope='All');data['csrf_token']=csrf
        r=c.post('/signup',data=data)
        check(r.status_code==302 and r.location.endswith('/login'),'Signup creates account and redirects to login')
        row=query_db('SELECT * FROM users WHERE username=%s',[data['username']],one=True)
        check(row['role']=='citizen' and row['district'] is None and row['mp_id'] is None and row['vendor_id'] is None,'Public role and scope tampering cannot grant official access')
        check(row['password_hash']!=password and check_password_hash(row['password_hash'],password),'Database stores a working password hash, not plaintext')
        check('Account created successfully' in c.get('/login').get_data(as_text=True),'Signup success message shown')
        check(c.post('/signup',data=data).status_code==400,'Duplicate username handled without overwriting user')
        check(login(c,data['username'],'WrongPassword').status_code==200 and c.get('/api/me').status_code==401,'Incorrect password cannot authenticate')
        check(login(c,data['username']).status_code==302 and c.get('/api/me').get_json()['user']['role']=='citizen','New citizen can log in using stored account')
        check(c.get('/users').status_code==403 and c.post('/users',data=data).status_code==403,'Citizen cannot read or submit account management')
        check(c.get('/api/risk-analysis').status_code==403,'New citizen retains restricted analysis permissions')
        a=app.test_client();login(a,'admin','admin123')
        csrf=token(a,'/users')
        check('User Accounts' in a.get('/').get_data(as_text=True),'Administrator navigation includes User Accounts')
        check(a.post('/users',data=payload('_no_csrf',role='citizen')).status_code==400,'Administrator form rejects missing CSRF')
        for role,scope in [('district_admin','Pune'),('ministry','Representative - Test'),('auditor',''),('vendor','Sunrise Infrastructure'),('citizen','')]:
            data=payload('_'+role,role=role,scope=scope);data['csrf_token']=csrf
            r=a.post('/users',data=data)
            check(r.status_code==302,'Administrator creates '+role+' through form')
            row=query_db('SELECT * FROM users WHERE username=%s',[data['username']],one=True)
            expected={'district_admin':('district',scope),'ministry':('mp_id',scope),'vendor':('vendor_id',scope)}
            check(row['role']==role and (role not in expected or row[expected[role][0]]==scope),'Saved role and scope: '+role)
            client=app.test_client();login(client,data['username'])
            check(client.get('/api/me').get_json()['user']['role']==role,'New '+role+' login works')
            check(client.get('/users').status_code==403,'New scoped/non-admin '+role+' cannot manage accounts')
        data=payload('_empty_vendor',role='vendor',scope='');data['csrf_token']=csrf
        check(a.post('/users',data=data).status_code==400,'Vendor account requires identifier')
        data=payload('_invalid_role',role='superadmin');data['csrf_token']=csrf
        check(a.post('/users',data=data).status_code==400,'Unknown role rejected')
        response=a.get('/users').get_data(as_text=True)
        check(prefix+'_auditor' in response and password not in response and row['password_hash'] not in response,'Account list shows users without passwords or hashes')
        other=app.test_client();check(other.post('/signup',data=payload('_cross',csrf_token=csrf)).status_code==400,'CSRF token is bound to the originating session')
        guest=app.test_client();check(guest.get('/users').status_code==302,'Anonymous account management redirects to login')
        print(json.dumps(dict(passed=len(checks),database='drishti_final_major_validation'),indent=2))
    finally:
        execute_db('DELETE FROM users WHERE LEFT(username,%s)=%s',[len(prefix),prefix])
    (P/'checks/ACCOUNT_TEST_RESULTS.json').write_text(json.dumps(dict(passed=len(checks),checks=checks,database='drishti_final_major_validation',test_users_cleaned_up=True),indent=2),encoding='utf-8')

if __name__=='__main__':main()
