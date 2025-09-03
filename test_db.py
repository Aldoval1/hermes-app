import pymongo
from pymongo.errors import ConnectionFailure

# --- PEGA TU URL DE MONGO ATLAS AQUÍ DENTRO DE LAS COMILLAS ---
MONGO_URI = 'mongodb+srv://...' 
# -----------------------------------------------------------

try:
    # Intenta crear un cliente de MongoDB
    client = pymongo.MongoClient(MONGO_URI)
    
    # El comando list_database_names() fuerza una conexión a la base de datos.
    client.list_database_names()
    
    print("\n✅ ¡Éxito! La conexión a MongoDB Atlas funcionó perfectamente.\n")

except ConnectionFailure as e:
    print(f"\n❌ ¡Error de Conexión! No se pudo conectar a la base de datos.")
    print(f"   Detalles del error: {e}\n")
except Exception as e:
    print(f"\n❌ ¡Ocurrió otro error!")
    print(f"   Detalles: {e}\n")