from pathlib import Path
import argparse
from config import Config
from init_db import init_database
from services.data_processor import process_and_save_dataset

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description='Import the master dataset and rebuild all analyses.')
    parser.add_argument('--format',choices=['excel','csv'],default='excel')
    args=parser.parse_args()
    file=Path(Config.MASTER_DATASET)
    if args.format=='csv': file=file.with_suffix('.csv')
    init_database()
    result=process_and_save_dataset(str(file))
    print(result)
    raise SystemExit(0 if result.get('success') else 1)
