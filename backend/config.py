# file: backend/config.py

import os

class Config:
    """Class để quản lý cấu hình cho ứng dụng Flask."""
    # SECRET_KEY cần thiết cho việc quản lý session của Flask
    USER_DATA_ROOT = os.environ.get('USER_DATA_ROOT', '/remotelab/userdata')
    SECRET_KEY = os.environ.get('SECRET_KEY', 'cc490060664a3e27a88ff574960614b580c00b58f8e1396289c67404309d9477')