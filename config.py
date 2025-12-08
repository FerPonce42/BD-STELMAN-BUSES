import MySQLdb
import MySQLdb.cursors

class Config:
    MYSQL_HOST = 'localhost'
    MYSQL_USER = 'root'
    MYSQL_PASSWORD = ''
    MYSQL_DB = 'bd_stelman_buses'
    MYSQL_CURSORCLASS = 'DictCursor'

def get_connection():
    return MySQLdb.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        passwd=Config.MYSQL_PASSWORD,
        db=Config.MYSQL_DB,
        cursorclass=MySQLdb.cursors.DictCursor
    )
