import os

TOKEN = "8296700796:AAFs5ZAA1HaE6AHObbhAUfMegl7TbCmmQaQ"

SUPER_ADMIN_ID = 716230412



# База даних
DB_USER = "aplotua_mainvs"
DB_PASSWORD = "~xMym54U~4"
DB_HOST = "aplotua.mysql.tools"
DB_PORT = 3306
DB_NAME = "aplotua_mainvs"
DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BROADCAST_FILES_DIR = os.path.join(BASE_DIR, "files/broadcast")


FACEBOOK_LINK = "https://www.facebook.com/vsmarketua"
INSTAGRAM_LINK = "https://www.instagram.com/vsmarket.ua/"
TIKTOK_LINK = "https://www.tiktok.com/@vsmarket.ua"