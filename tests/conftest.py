"""
Configuración común de los tests del Decretómetro.

Hace dos cosas:
1. Agrega la raíz del proyecto a sys.path (para poder hacer `import database`).
2. AÍSLA la base de datos: en vez de usar `decretometro.db` (la real), los tests
   trabajan sobre una COPIA descartable guardada en `tests/.tmp/`.

Funciona tanto con `python -m pytest` como ejecutando un test directamente
(`python tests/test_sac.py`), siempre que el test haga `import conftest` al inicio.
"""
import os
import shutil
import sys

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TESTS_DIR)
TMP_DIR = os.path.join(TESTS_DIR, ".tmp")
PROD_DB = os.path.join(PROJECT_ROOT, "decretometro.db")

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import database as db  # noqa: E402


def preparar_base_temporal(db_module, nombre="base_prueba.db"):
    """Copia la base real a tests/.tmp/<nombre> y apunta database.DB_PATH a esa copia."""
    os.makedirs(TMP_DIR, exist_ok=True)
    destino = os.path.join(TMP_DIR, nombre)
    for sufijo in ("", "-wal", "-shm"):
        try:
            os.remove(destino + sufijo)
        except FileNotFoundError:
            pass
    if os.path.exists(PROD_DB):
        shutil.copy2(PROD_DB, destino)
    db_module.DB_PATH = destino
    # Salvaguarda: nunca permitir que un test apunte a la base real.
    assert os.path.abspath(db_module.DB_PATH) != os.path.abspath(PROD_DB), \
        "Los tests no pueden usar la base de datos real."
    return destino


# Aislamiento inmediato al importar este módulo: cubre también los tests que
# ejecutan código al importarse (p. ej. test_backend.py llama a db.init_db()).
preparar_base_temporal(db, "base_sesion.db")


@pytest.fixture(autouse=True)
def base_aislada(request):
    """Cada test arranca con una copia limpia de la base real; la real no se toca.

    Los módulos que ya manejan su propia base aislada (definen TEST_DB_PATH y la
    configuran en setUpClass) no se tocan: su ciclo de vida ya es independiente.
    """
    if hasattr(request.module, "TEST_DB_PATH"):
        yield
        return
    anterior = db.DB_PATH
    preparar_base_temporal(db, "base_prueba.db")
    yield
    db.DB_PATH = anterior
