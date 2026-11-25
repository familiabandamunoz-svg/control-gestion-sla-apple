# Control de Gestión y SLA — Soporte Apple (Flask + SQLite)

Aplicación web autocontenida en **Python (Flask)** y **SQLite** para el control operacional de Incidentes (`INC`) y Requerimientos (`Tasks`) exportados desde reportes tabulares de ServiceNow / Solver, incluyendo cálculo de duración hábil, evaluación de SLA y visualización de KPIs.

> **Aviso:** Este repositorio contiene únicamente el código fuente y estructura de referencia. No incluye datos operativos reales, reportes Excel ni bases de datos con información corporativa.

## Características principales
- **Autenticación y roles:** Login con `Flask-Login`, contraseñas hasheadas con `Werkzeug` y creación de usuarios para rol `admin`.
- **Importación y normalización de reportes Excel:** Procesa hojas de incidentes y requerimientos, normaliza nombres de especialistas, extrae responsables desde notas de cierre cuando faltan y calcula tiempos hábiles.
- **Evaluación de SLA y KPIs:** Calcula cumplimiento de SLA por tipo de caso (meta por defecto de `24h` en incidentes y `72h` en requerimientos), mediana y promedio de horas, backlog, reasignaciones y gráficos interactivos con `Chart.js`.
- **Gestión manual y cierre de casos:** Registro de tickets desde modal y cierre rápido con cálculo de horas transcurridas.

## Estructura del proyecto
```text
gestion_apple_bch/
├── .gitignore
├── README.md
├── requirements.txt
├── app.py
├── parser_solver.py
├── test_parser.py
└── templates/
    ├── login.html
    └── dashboard.html
```

## Puesta en marcha en local

### Windows (PowerShell)
```powershell
git clone https://github.com/<TU_USUARIO>/<TU_REPOSITORIO>.git
cd <TU_REPOSITORIO>
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SECRET_KEY="cambia-esta-clave-en-produccion"
py app.py
```

### macOS / Linux
```bash
git clone https://github.com/<TU_USUARIO>/<TU_REPOSITORIO>.git
cd <TU_REPOSITORIO>
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="cambia-esta-clave-en-produccion"
python app.py
```

Abre `http://127.0.0.1:5000` en tu navegador e inicia sesión con las credenciales iniciales de prueba (`admin` / `Admin2026!`), cambiando la contraseña y `SECRET_KEY` antes de exponerlo en cualquier red.

## Pruebas unitarias
```bash
python -m unittest discover -v
```
