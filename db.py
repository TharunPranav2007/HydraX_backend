import psycopg2

def get_connection():
    return psycopg2.connect(
        host="localhost",
        database="groundwater_db",
        user="postgres",
        password="TP007"
    )