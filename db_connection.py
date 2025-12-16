import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()


def get_connection():
    """Crea y retorna una conexión a la base de datos MariaDB"""
    try:
        host = os.getenv("DB_HOST")
        user = os.getenv("DB_USER")
        password = os.getenv("DB_PASSWORD")
        database = os.getenv("DB_NAME")
        port = int(os.getenv("DB_PORT", 3306))
        
        connection = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=port,
            autocommit=True
        )
        return connection
    except Error as e:
        print(f"Error de conexión (código {e.errno}): {e.msg}")
        return None
    except Exception as e:
        print(f"Error general: {type(e).__name__}: {e}")
        return None


def test_connection():
    """Prueba la conexión a MariaDB"""
    connection = get_connection()
    
    if connection and connection.is_connected():
        db_info = connection.get_server_info()
        print(f"✅ Conectado a MariaDB versión {db_info}")
        
        cursor = connection.cursor()
        cursor.execute("SELECT DATABASE();")
        db_name = cursor.fetchone()
        print(f"Base de datos actual: {db_name[0]}")
        cursor.close()
        
        connection.close()
        return True
    else:
        print("❌ No se pudo conectar a MariaDB")
        return False


if __name__ == '__main__':
    test_connection()
