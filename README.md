# Consolidador de impacto social

Prototipo Streamlit para importar CSV/Excel, mapear columnas heterogéneas, revisar calidad, asignar IDs persistentes con SQLite y explorar indicadores separados por tipo de actividad.

## Ejecutar

    python -m pip install -r requirements.txt
    streamlit run app.py

Usa el botón de demo para mostrar dos fuentes sintéticas. La identificación tentativa usa nombre normalizado, nacimiento y municipio; revisa falsos positivos antes de publicar cifras. El CSV exportado conserva fuente, fila original, calidad e ID. Los eventos repetidos se marcan para revisión, nunca se borran automáticamente.
