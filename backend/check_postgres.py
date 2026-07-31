
import psycopg2
from app.core.config import settings

def check_postgres():
    try:
        conn = psycopg2.connect(
            host=settings.POSTGRES_SERVER,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            dbname=settings.POSTGRES_DB,
            port=settings.POSTGRES_PORT,
            connect_timeout=3
        )
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM reports;")
        count = cur.fetchone()[0]
        print(f"Connected to PostgreSQL! Reports count: {count}")
        conn.close()
    except Exception as e:
        print(f"PostgreSQL connection failed: {e}")

if __name__ == "__main__":
    check_postgres()
