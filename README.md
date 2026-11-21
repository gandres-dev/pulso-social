# Consolidador de impacto social

Interfaz Streamlit para importar CSV/Excel, armonizar campos de distintas fuentes y comparar la cobertura de Tamizaje Rosa y Melenas en Movimiento.

## Ejecutar

    python -m pip install -r requirements.txt
    streamlit run app.py

Pulsa **Cargar fuentes de demostración** para abrir el Excel maestro de Tamizaje Rosa y el CSV maestro de Melenas en Movimiento. También puedes cargar archivos CSV o Excel propios y revisar el mapeo de columnas en **Preparación de fuentes**.

## Indicadores y gráficos

- Personas únicas por ID interno, registros/movimientos y unidades reportadas.
- Periodo mensual: registros frente a personas únicas.
- Cobertura por estado y municipio.
- Conteos por servicio y tipo de actividad.
- Tamizaje Rosa: mastografías, ultrasonidos, Papanicolaou, atenciones de nutrición y distribución de resultados sintéticos.
- Melenas en Movimiento: donaciones, gestiones, pelucas entregadas y revisión de trenzas menores a 30 cm.
- Calidad: campos faltantes, periodos/fechas inválidos, cantidades inválidas, trenzas bajo el mínimo y eventos repetidos probables.
- Exportación CSV con fuente, número de fila, ID interno, atributos originales y calidad; resumen JSON con filtros, corte y denominador.

## Criterios de lectura

El corte de actividad corresponde a la fecha más reciente dentro de los filtros. El denominador de personas es el número de IDs internos únicos en esos registros; registros y unidades no equivalen a personas. Los eventos repetidos se señalan para revisión y no se eliminan automáticamente. Los resultados clínicos y datos personales de los archivos de demostración son sintéticos.
