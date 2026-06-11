import os
from contextlib import contextmanager
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    return psycopg2.connect(os.environ["DATABASE_URL"])


@contextmanager
def cursor():
    conn = get_connection()
    try:
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
    finally:
        conn.close()


def apply_schema():
    schema = (Path(__file__).parent / "schema.sql").read_text()
    with cursor() as cur:
        cur.execute(schema)
    print("Schema applied.")


if __name__ == "__main__":
    apply_schema()
