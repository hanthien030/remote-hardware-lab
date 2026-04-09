# file: backend/app/db.py

import mysql.connector
import os
from flask import g


def _db_config():
    return {
        'host': os.environ.get('DB_HOST'),
        'user': os.environ.get('DB_USER'),
        'password': os.environ.get('DB_PASSWORD'),
        'database': os.environ.get('DB_NAME'),
    }


def get_db_connection():
    """
    Táº¡o vÃ  quáº£n lÃ½ káº¿t ná»‘i CSDL.
    Sá»­ dá»¥ng g object cá»§a Flask Ä‘á»ƒ lÆ°u káº¿t ná»‘i trong má»™t request context.
    """
    if 'db' not in g:
        g.db = mysql.connector.connect(**_db_config())
    return g.db


def create_db_connection():
    """
    Táº¡o káº¿t ná»‘i CSDL trự̣c tiếp cho background worker / non-request code.
    KhÃ´ng dÃ¹ng Flask g.
    """
    return mysql.connector.connect(**_db_config())


def close_db_connection(e=None):
    """ÄÃ³ng káº¿t ná»‘i CSDL khi request káº¿t thÃºc."""
    db = g.pop('db', None)
    if db is not None:
        db.close()
