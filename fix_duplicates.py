# fix_duplicates.py

from models.database import get_db
from crud.operations import DBOperations

db = next(get_db())
db_ops = DBOperations(db)
db_ops.normalize_existing_paths()
print("Дубликаты удалены, пути нормализованы")
