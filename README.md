# Consolidador de impacto social
Herramienta que reúna datos de diferentes programas y fuentes, facilite su validación y permita a dirección y coordinaciones producir indicadores e informes confiables.

## Ejecución de manera local

    # Crear entorno virtual
    python3 -m venv .venv
    # Activiar tu entorno
    source .venv/bin/activate
    # Instalar las paqueteria necesarias
    python -m pip install -r requirements.txt
    # Ejecutar la aplicación
    streamlit run app.py

## Ejecución en la nube
Ingresa a la siguiente página (se sincroniza con todos los cambios que se hagan en el repositorio):

[https://impulso-social.streamlit.app/](https://impulso-social.streamlit.app/)

## Uso
Para usar la aplicacion se deben de subir fuentes de información para generar indicadores y resumenes. La aplicación acepta archivos xlsx y csv y se pueden subir varios archivos a la vez.

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
