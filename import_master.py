from config import Config
from init_db import init_database
from services.data_processor import process_and_save_dataset
if __name__=='__main__':
    init_database()
    result=process_and_save_dataset(Config.MASTER_DATASET)
    print(result)
    raise SystemExit(0 if result.get('success') else 1)
