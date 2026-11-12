"""Explicit additive SQLite migration; no import of operational engine or app.main."""
import argparse
from pathlib import Path
from sqlalchemy import create_engine


def migrate(engine):
    if engine.dialect.name != 'sqlite':
        raise ValueError('SQLite required')
    with engine.connect() as connection:
        connection.exec_driver_sql('BEGIN IMMEDIATE')
        try:
            columns = {r[1]:r for r in connection.exec_driver_sql('PRAGMA table_info(beers)')}
            # Accept historical TEXT/BOOLEAN nullable schemas as well as current ORM.
            if not {'id','is_available','is_deleted','tap_position'}.issubset(columns):
                raise ValueError('Existing beer table required')
            if 'tap_entered_at' in columns:
                row = columns['tap_entered_at']
                if row[2].upper()!='DATETIME' or row[3] or row[4] is not None or row[5]:
                    raise ValueError('Incompatible tap entry column')
                added = False
            else:
                connection.exec_driver_sql('ALTER TABLE beers ADD COLUMN tap_entered_at DATETIME')
                added = True
            connection.commit()
            return added
        except BaseException:
            connection.rollback()
            raise


def main():
    parser = argparse.ArgumentParser(description='Add nullable Tap entry timestamp; back up before running')
    parser.add_argument('--database',type=Path,required=True)
    args = parser.parse_args()
    path = args.database.resolve(strict=True)
    if not path.is_file():
        parser.error('Existing SQLite file required')
    engine = create_engine('sqlite:///'+path.as_posix(),connect_args={'timeout':15})
    try:
        added = migrate(engine)
        print('Tap entry migration complete; column added' if added else 'Tap entry schema already current')
    except Exception:
        print('Tap entry migration failed; transaction rolled back; inspect offline')
        return 1
    finally:
        engine.dispose()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
