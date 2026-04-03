import psycopg
from config import DATABASE_URL


def get_connection():
    return psycopg.connect(DATABASE_URL)
