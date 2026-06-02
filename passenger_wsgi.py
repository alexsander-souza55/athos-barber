import sys
import os

# Garante que o Python encontra os modulos do projeto
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

# Carrega as variaveis do .env antes de importar o app
from dotenv import load_dotenv
load_dotenv(os.path.join(_here, '.env'))

# Importa o app Flask como "application" (nome exigido pelo Passenger/Hostinger)
from wsgi import app as application
