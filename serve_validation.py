import os
os.environ['DB_NAME']='drishti_master_validation_v3'
from app import app
if __name__=='__main__':
    import sys
    app.run(host='127.0.0.1',port=int(sys.argv[1]) if len(sys.argv)>1 else 5057,debug=False,threaded=True)
