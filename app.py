import html
import json
import re
import sqlite3
import unicodedata
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).with_name("impacto.db")
DATA_DIR = Path(__file__).with_name("datos_sinteticos")

FIELDS = {
    "person_name": "Nombre de la persona",
    "source_person_id": "ID de origen (opcional)",
    "birth_date": "Fecha de nacimiento",
    "municipality": "Municipio",
    "state": "Estado",
    "program": "Programa",
    "period": "Periodo / mes",
    "program_date": "Fecha de realización",
    "activity_type": "Tipo de actividad",
    "service": "Servicio",
    "quantity": "Cantidad",
}

ALIASES = {
    "person_name": ["nombre", "beneficiario", "persona", "nombre completo"],
    "source_person_id": ["id paciente", "id persona", "id participante", "id beneficiario"],
    "birth_date": ["nacimiento", "fecha de nacimiento", "fecha nacimiento"],
    "municipality": ["municipio", "alcaldia", "localidad"],
    "state": ["estado", "entidad federativa"],
    "program": ["programa", "programa social"],
    "period": ["periodo", "mes", "period"],
    "program_date": ["fecha de realizacion del programa", "fecha de atencion", "fecha de movimiento", "fecha cita"],
    "activity_type": ["tipo", "actividad", "tipo de actividad"],
    "service": ["servicio", "apoyo", "insumo", "concepto"],
    "quantity": ["cantidad", "atenciones", "unidades"],
}

st.set_page_config(page_title="Impacto Social | EIRA", page_icon="🌱", layout="wide")

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.6rem; padding-bottom: 2.4rem;}
      [data-testid="stMetric"] {background:#f6f8fa; border:1px solid #e6eaf0; padding:14px 16px; border-radius:12px;}
      h1 {letter-spacing:-0.03em;}
      .small-muted {color:#667085; font-size:0.9rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


def norm(value):
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value).strip().lower())
    return re.sub(r"[^a-z0-9]+", "", "".join(c for c in text if not unicodedata.combining(c)))


def open_db():
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "CREATE TABLE IF NOT EXISTS people_v2 (person_id TEXT PRIMARY KEY, name_key TEXT, birth_key TEXT, municipality_key TEXT, state_key TEXT)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS record_ids (source TEXT, source_row INTEGER, person_id TEXT, PRIMARY KEY(source,source_row))"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS audit_v2 (at TEXT DEFAULT CURRENT_TIMESTAMP, action TEXT, record_id TEXT, old_value TEXT, new_value TEXT)"
    )
    con.commit()
    return con


def period_key(value):
    if value is None or pd.isna(value) or not str(value).strip():
        return ""
    text = str(value).strip()
    match = re.fullmatch(r"(20\d{2})[-/](0?[1-9]|1[0-2])", text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}"
    dt = pd.to_datetime(value, errors="coerce", dayfirst=True)
    return dt.strftime("%Y-%m") if pd.notna(dt) else ""


def load_frame(file_name, payload):
    if file_name.lower().endswith(".csv"):
        return pd.read_csv(payload)
    return pd.read_excel(payload, sheet_name=0)


def load_demo_frames():
    paths = [
        DATA_DIR / "tamizaje_rosa_sintetico.xlsx",
        DATA_DIR / "melenas_en_movimiento_sintetico.csv",
    ]
    frames = {}
    for path in paths:
        if not path.exists():
            st.error(f"No encontré el archivo de demostración: {path.name}")
            continue
        try:
            frames[path.name] = pd.read_excel(path, sheet_name=0) if path.suffix == ".xlsx" else pd.read_csv(path)
        except Exception as exc:
            st.error(f"No pude abrir {path.name}: {exc}")
    return frames


def guess_column(columns, field):
    aliases = {norm(alias) for alias in ALIASES[field]}
    for column in columns:
        normalized = norm(column)
        if normalized in aliases:
            return column
    for column in columns:
        normalized = norm(column)
        if any(alias in normalized for alias in aliases if len(alias) > 5):
            return column
    return "(sin mapear)"


def read_extra(row, mapped_columns):
    extras = {}
    for key, value in row.items():
        if key in mapped_columns or pd.isna(value):
            continue
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        elif hasattr(value, "item"):
            value = value.item()
        extras[str(key)] = value
    return json.dumps(extras, ensure_ascii=False, default=str)


def prepare_data(frames, mappings):
    pieces = []
    for source, frame in frames.items():
        mapping = mappings[source]
        hair_column = next((col for col in frame.columns if "longituddetrenza" in norm(col)), None)
        mapped_columns = [col for col in mapping.values() if col != "(sin mapear)"]
        for row_number, row in frame.iterrows():
            record = {field: row[column] if column != "(sin mapear)" else "" for field, column in mapping.items()}
            record["source_attributes"] = read_extra(row, mapped_columns)
            record["hair_length_cm"] = pd.to_numeric(row[hair_column], errors="coerce") if hair_column else pd.NA
            record["source"] = source
            record["source_row"] = int(row_number) + 2
            pieces.append(record)

    if not pieces:
        return pd.DataFrame()

    data = pd.DataFrame(pieces)
    for col in ["person_name", "municipality", "state", "program", "period", "activity_type", "service", "source_person_id"]:
        data[col] = data[col].fillna("").astype(str).str.strip()

    data["birth_date"] = pd.to_datetime(data["birth_date"], errors="coerce", dayfirst=True)
    data["program_date"] = pd.to_datetime(data["program_date"], errors="coerce", dayfirst=True)
    data["hair_length_cm"] = pd.to_numeric(data["hair_length_cm"], errors="coerce")
    raw_period = data["period"].fillna("").astype(str).str.strip()
    parsed_period = raw_period.map(period_key)
    blank_period = raw_period.eq("")
    data["period"] = parsed_period
    data.loc[blank_period, "period"] = data.loc[blank_period, "program_date"].dt.strftime("%Y-%m").fillna("")
    data["quantity"] = pd.to_numeric(data["quantity"], errors="coerce")
    data["quality"] = "OK"

    required = [
        ("person_name", "falta nombre"),
        ("municipality", "falta municipio"),
        ("state", "falta estado"),
        ("program", "falta programa"),
        ("period", "periodo inválido o faltante"),
        ("activity_type", "falta tipo de actividad"),
        ("service", "falta servicio"),
    ]
    for column, issue in required:
        data.loc[data[column].eq(""), "quality"] += " · " + issue
    data.loc[data["quantity"].isna() | data["quantity"].le(0), "quality"] += " · cantidad inválida"
    data.loc[data["program_date"].isna(), "quality"] += " · fecha de realización faltante"

    is_melenas = data["program"].map(norm).eq("melenasenmovimiento")
    is_donation = data["activity_type"].map(norm).str.contains("donacion", na=False)
    too_short = is_melenas & is_donation & data["hair_length_cm"].notna() & data["hair_length_cm"].lt(30)
    data.loc[too_short, "quality"] += " · trenza menor a 30 cm"

    data["person_key"] = data.apply(
        lambda row: (
            norm(row["person_name"]),
            row["birth_date"].strftime("%Y-%m-%d") if pd.notna(row["birth_date"]) else "",
            norm(row["municipality"]),
        ),
        axis=1,
    )
    return assign_person_ids(data)


def assign_person_ids(data):
    con = open_db()
    people = con.execute("SELECT person_id,name_key,birth_key,municipality_key,state_key FROM people_v2").fetchall()
    lookup = {(row[1], row[2], row[3], row[4]): row[0] for row in people}
    result = []

    for row in data.itertuples():
        name_key, birth_key, municipality_key = row.person_key
        if not name_key:
            result.append("")
            continue

        saved = con.execute(
            "SELECT person_id FROM record_ids WHERE source=? AND source_row=?",
            (row.source, row.source_row),
        ).fetchone()
        if saved:
            result.append(saved[0])
            continue

        state_key = norm(row.state)
        key = (name_key, birth_key, municipality_key, state_key)
        person_id = lookup.get(key)
        if not person_id:
            person_id = "PER-" + uuid.uuid4().hex[:10].upper()
            con.execute(
                "INSERT INTO people_v2(person_id,name_key,birth_key,municipality_key,state_key) VALUES (?,?,?,?,?)",
                (person_id, name_key, birth_key, municipality_key, state_key),
            )
            lookup[key] = person_id
        con.execute(
            "INSERT OR REPLACE INTO record_ids(source,source_row,person_id) VALUES (?,?,?)",
            (row.source, row.source_row, person_id),
        )
        result.append(person_id)

    con.commit()
    con.close()
    data["person_id"] = result

    event_key = ["person_id", "program", "period", "activity_type", "service"]
    repeated = data.duplicated(event_key, keep=False) & data["person_name"].ne("")
    data.loc[repeated, "quality"] += " · posible evento duplicado"
    return data


def get_attr(data, field_name):
    target = norm(field_name)
    values = []
    for raw in data["source_attributes"]:
        try:
            attrs = json.loads(raw) if raw else {}
        except (TypeError, json.JSONDecodeError):
            attrs = {}
        value = next((v for k, v in attrs.items() if norm(k) == target), None)
        values.append(value)
    return pd.Series(values, index=data.index)


def quality_counts(data):
    flags = data.loc[data["quality"].ne("OK")].copy()
    return flags


def default_mappings(frames):
    return {
        source: {field: guess_column(frame.columns, field) for field in FIELDS}
        for source, frame in frames.items()
    }


def add_insight(text, detail=None):
    safe_text = html.escape(str(text))
    safe_detail = html.escape(str(detail or ""))
    st.markdown(
        f'<div style="padding:14px 16px;border:1px solid #e5eaf0;border-radius:12px;background:#fff;margin:4px 0 8px 0;">'
        f'<div style="font-weight:650;color:#1d2939;">{safe_text}</div>'
        f'<div style="font-size:0.9rem;color:#667085;margin-top:4px;">{safe_detail}</div></div>',
        unsafe_allow_html=True,
    )


def count_service(data, needles):
    normalized = data["service"].map(norm)
    matches = normalized.map(lambda value: any(norm(needle) in value for needle in needles))
    return int(matches.sum())


st.title("🌱 Impacto social")
st.caption("Consolida las fuentes de Tamizaje Rosa y Melenas en Movimiento; explora cobertura, servicios y calidad.")

with st.sidebar:
    st.header("Fuentes")
    demo_clicked = st.button("Cargar fuentes de demostración", use_container_width=True, type="primary")
    uploaded = st.file_uploader("O importa CSV o Excel", type=["csv", "xlsx", "xls"], accept_multiple_files=True)
    if st.button("Limpiar sesión", use_container_width=True):
        st.session_state.pop("frames", None)
        st.rerun()
    st.divider()
    st.caption("La demostración carga el Excel maestro de Tamizaje Rosa y el CSV maestro de Melenas en Movimiento.")

if demo_clicked:
    st.session_state.frames = load_demo_frames()

if uploaded:
    imported = {}
    for file in uploaded:
        try:
            imported[file.name] = load_frame(file.name, file)
        except Exception as exc:
            st.error(f"No pude leer {file.name}: {exc}")
    if imported:
        st.session_state.frames = imported

frames = st.session_state.get("frames", {})
if not frames:
    st.info("Carga las fuentes o selecciona la demostración para abrir el tablero.")
    st.stop()

st.markdown("#### Fuentes cargadas")
source_cols = st.columns(min(4, max(1, len(frames))))
for index, (name, frame) in enumerate(frames.items()):
    with source_cols[index % len(source_cols)]:
        st.metric(name, f"{len(frame):,} filas")

st.caption("Las columnas comunes se reconocen automáticamente por el nombre del encabezado.")
mappings = default_mappings(frames)
unmapped_core = []
for source, mapping in mappings.items():
    for field in ["person_name", "municipality", "program", "period", "activity_type", "service"]:
        if mapping.get(field) == "(sin mapear)":
            unmapped_core.append(f"{source}: {FIELDS[field]}")
if unmapped_core:
    st.warning("No pude detectar automáticamente algunos campos comunes. Renombra sus encabezados y vuelve a cargar la fuente: " + "; ".join(unmapped_core[:5]))
data = prepare_data(frames, mappings)
if data.empty:
    st.warning("No hay registros para analizar.")
    st.stop()

# Filters
st.subheader("Filtros")
program_options = sorted(data["program"][data["program"].ne("")].unique())
period_options = sorted(data["period"][data["period"].ne("")].unique())
state_options = sorted(data["state"][data["state"].ne("")].unique())
municipality_options = sorted(data["municipality"][data["municipality"].ne("")].unique())
type_options = sorted(data["activity_type"][data["activity_type"].ne("")].unique())
service_options = sorted(data["service"][data["service"].ne("")].unique())
source_options = sorted(data["source"].unique())

st.caption("Deja un filtro vacío para incluir todas sus opciones.")
filter_cols = st.columns(4)
program_selected = filter_cols[0].multiselect("Programa", program_options, placeholder="Todos", key="f-program")
period_selected = filter_cols[1].multiselect("Periodo", period_options, placeholder="Todos", key="f-period")
state_selected = filter_cols[2].multiselect("Estado", state_options, placeholder="Todos", key="f-state")
municipality_selected = filter_cols[3].multiselect("Municipio", municipality_options, placeholder="Todos", key="f-municipality")
filter_cols_2 = st.columns(3)
type_selected = filter_cols_2[0].multiselect("Tipo de actividad", type_options, placeholder="Todos", key="f-type")
service_selected = filter_cols_2[1].multiselect("Servicio", service_options, placeholder="Todos", key="f-service")
source_selected = filter_cols_2[2].multiselect("Fuente", source_options, placeholder="Todas", key="f-source")
program_filter = program_selected or program_options
period_filter = period_selected or period_options
state_filter = state_selected or state_options
municipality_filter = municipality_selected or municipality_options
type_filter = type_selected or type_options
service_filter = service_selected or service_options
source_filter = source_selected or source_options

filtered = data[
    data["program"].isin(program_filter)
    & data["period"].isin(period_filter)
    & data["state"].isin(state_filter)
    & data["municipality"].isin(municipality_filter)
    & data["activity_type"].isin(type_filter)
    & data["service"].isin(service_filter)
    & data["source"].isin(source_filter)
].copy()
count_data = filtered.assign(
    person_count_id=filtered["person_id"].where(filtered["person_id"].ne(""), pd.NA)
)

# Tabs share the filtered frame.
dashboard_tab, quality_tab, records_tab = st.tabs(["Resumen e insights", "Calidad y ajustes", "Registros y exportación"])

with dashboard_tab:
    if filtered.empty:
        st.info("No hay registros con esa combinación de filtros.")
    else:
        people_count = filtered.loc[filtered["person_id"].ne(""), "person_id"].nunique()
        event_count = len(filtered)
        units = filtered["quantity"].sum(min_count=1)
        state_count = filtered.loc[filtered["state"].ne(""), "state"].nunique()
        municipality_count = filtered.loc[filtered["municipality"].ne(""), "municipality"].nunique()
        cutoff = filtered["program_date"].max()
        cutoff_label = cutoff.strftime("%d/%m/%Y") if pd.notna(cutoff) else "sin fecha válida"

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Personas únicas", f"{people_count:,}")
        k2.metric("Registros / movimientos", f"{event_count:,}")
        k3.metric("Unidades reportadas", f"{int(units):,}" if pd.notna(units) else "—")
        k4.metric("Estados cubiertos", f"{state_count:,}")
        k5.metric("Municipios cubiertos", f"{municipality_count:,}")

        st.caption(
            f"Corte de actividad: {cutoff_label} · Denominador de personas: IDs internos únicos dentro del filtro · "
            f"Fuentes seleccionadas: {len(filtered['source'].unique())} · Filas por revisar: {int(filtered['quality'].ne('OK').sum()):,}."
        )

        # Concise rule-based insights
        monthly = count_data.loc[count_data["period"].ne("")].groupby("period").agg(
            registros=("source_row", "size"),
            personas=("person_count_id", "nunique"),
        ).sort_index()
        service_counts = count_data.groupby("service").agg(
            registros=("source_row", "size"),
            personas=("person_count_id", "nunique"),
        ).sort_values("registros", ascending=False)
        municipality_counts = count_data.loc[count_data["municipality"].ne("")].groupby("municipality").agg(
            registros=("source_row", "size"),
            personas=("person_count_id", "nunique"),
        ).sort_values("registros", ascending=False)
        repeated_people = int((filtered.loc[filtered["person_id"].ne(""), "person_id"].value_counts() > 1).sum())
        most_common_service = service_counts.index[0] if not service_counts.empty else "—"
        most_common_service_n = int(service_counts.iloc[0]["registros"]) if not service_counts.empty else 0
        busiest_month = monthly["registros"].idxmax() if not monthly.empty else "—"
        busiest_month_n = int(monthly.loc[busiest_month, "registros"]) if not monthly.empty else 0
        top_municipality = municipality_counts.index[0] if not municipality_counts.empty else "—"
        top_municipality_n = int(municipality_counts.iloc[0]["registros"]) if not municipality_counts.empty else 0

        left, right = st.columns(2)
        with left:
            add_insight(
                f"Servicio con más registros: {most_common_service}",
                f"{most_common_service_n:,} movimientos dentro de los filtros actuales.",
            )
            add_insight(
                f"Mes con más actividad: {busiest_month}",
                f"{busiest_month_n:,} registros; la serie usa el periodo mapeado.",
            )
        with right:
            add_insight(
                f"Municipio con más actividad: {top_municipality}",
                f"{top_municipality_n:,} registros dentro de los filtros actuales.",
            )
            add_insight(
                f"Personas con más de un registro: {repeated_people:,}",
                "Es una señal de seguimiento o recurrencia; no se interpreta como personas adicionales.",
            )

        program_summary = count_data.groupby("program").agg(
            registros=("source_row", "size"),
            personas_unicas=("person_count_id", "nunique"),
            estados=("state", lambda values: values[values.ne("")].nunique()),
            municipios=("municipality", lambda values: values[values.ne("")].nunique()),
            servicios=("service", lambda values: values[values.ne("")].nunique()),
        ).reset_index()
        st.markdown("#### Comparación por programa")
        st.dataframe(program_summary, use_container_width=True, hide_index=True)

        st.markdown("#### Actividad en el tiempo")
        chart_left, chart_right = st.columns(2)
        with chart_left:
            if not monthly.empty:
                st.line_chart(monthly[["registros", "personas"]], height=300)
                st.caption("Registros frente a personas únicas por periodo. Una persona puede recibir varios servicios.")
            else:
                st.info("No hay periodos válidos para graficar.")
        with chart_right:
            if not service_counts.empty:
                st.bar_chart(service_counts.head(10)[["registros"]], height=300)
                st.caption("Servicios con más registros en la selección.")
            else:
                st.info("No hay servicios para graficar.")

        st.markdown("#### Cobertura territorial y tipo de actividad")
        geo_left, geo_right = st.columns(2)
        with geo_left:
            state_summary = count_data.loc[count_data["state"].ne("")].groupby("state").agg(
                registros=("source_row", "size"),
                personas=("person_count_id", "nunique"),
            ).sort_values("registros", ascending=False)
            if not state_summary.empty:
                st.bar_chart(state_summary, height=300)
                st.caption("El denominador de personas es IDs únicos por estado.")
        with geo_right:
            activity_summary = filtered.groupby("activity_type").agg(
                registros=("source_row", "size"),
                unidades=("quantity", "sum"),
            ).sort_values("registros", ascending=False)
            if not activity_summary.empty:
                st.bar_chart(activity_summary, height=300)
                st.caption("Los tipos conservan la clasificación original de cada fuente.")

        programs_in_view = sorted(filtered["program"].unique())
        if any("tamizaje" in norm(program) for program in programs_in_view):
            st.markdown("#### Indicadores de Tamizaje Rosa")
            rosa_data = filtered[filtered["program"].map(norm).str.contains("tamizaje")]
            cards = st.columns(4)
            cards[0].metric("Mastografías (registros)", count_service(rosa_data, ["mastografia"]))
            cards[1].metric("Ultrasonidos (registros)", count_service(rosa_data, ["ultrasonido", "usg"]))
            cards[2].metric("Papanicolaou (registros)", count_service(rosa_data, ["papanicolaou"]))
            cards[3].metric("Atenciones de nutrición", count_service(rosa_data, ["nutricion"]))
            st.caption("Los resultados clínicos incluidos en los datos de demostración son sintéticos.")

            result_fields = ["Resultado de USG", "Resultado de Papanicolaou", "Resultado de nutricion"]
            result_tables = []
            for field in result_fields:
                series = get_attr(rosa_data, field).dropna().astype(str)
                series = series[series.str.strip().ne("")]
                if not series.empty:
                    result_tables.append((field, series.value_counts().rename("registros").to_frame()))
            if result_tables:
                result_cols = st.columns(len(result_tables))
                for col, (field, table) in zip(result_cols, result_tables):
                    with col:
                        st.markdown(f"**{field}**")
                        st.dataframe(table, use_container_width=True)

        if any("melenas" in norm(program) for program in programs_in_view):
            st.markdown("#### Indicadores de Melenas en Movimiento")
            melena_data = filtered[filtered["program"].map(norm).str.contains("melenas")]
            donation = melena_data["activity_type"].map(norm).str.contains("donacion", na=False)
            deliveries = melena_data["activity_type"].map(norm).str.contains("entrega", na=False)
            short_braids = melena_data["hair_length_cm"].notna() & melena_data["hair_length_cm"].lt(30)
            cards = st.columns(4)
            cards[0].metric("Registros de donación", int(donation.sum()))
            cards[1].metric("Pelucas entregadas", int(deliveries.sum()))
            cards[2].metric("Trenzas bajo 30 cm", int(short_braids.sum()))
            cards[3].metric("Pacientes en seguimiento", int(melena_data["activity_type"].map(norm).str.contains("gestion|seguimiento", regex=True, na=False).sum()))
            if melena_data["hair_length_cm"].notna().any():
                hair_chart = melena_data.loc[melena_data["hair_length_cm"].notna(), ["hair_length_cm"]].copy()
                hair_chart["Rango"] = pd.cut(hair_chart["hair_length_cm"], bins=[0, 29, 39, 49, 100], labels=["<30", "30–39", "40–49", "50+"])
                hair_counts = hair_chart["Rango"].value_counts().sort_index().rename("trenzas").to_frame()
                st.bar_chart(hair_counts, height=250)
                st.caption("Longitud reportada de trenza, en centímetros; menos de 30 cm requiere revisión.")
with quality_tab:
    st.subheader("Revisión de calidad")
    st.caption("El ID de origen se conserva como referencia. El ID interno se concilia con nombre, nacimiento, municipio y estado; revisa posibles homónimos antes de interpretar resultados.")
    flags = quality_counts(data)
    q1, q2, q3 = st.columns(3)
    q1.metric("Filas importadas", f"{len(data):,}")
    q2.metric("Filas con alguna alerta", f"{len(flags):,}")
    q3.metric("Eventos duplicados probables", f"{int(data['quality'].str.contains('posible evento duplicado').sum()):,}")
    if not flags.empty:
        st.dataframe(
            flags[["source", "source_row", "person_name", "program", "state", "municipality", "period", "service", "hair_length_cm", "quality"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success("No hay alertas con las reglas aplicadas.")

    st.markdown("#### Ajustar IDs internos")
    st.caption("Edita solamente el ID interno; cada cambio queda en la bitácora local.")
    editor_cols = ["person_id", "person_name", "birth_date", "state", "municipality", "program", "period", "service", "source", "source_row", "quality"]
    editor_data = data[editor_cols].copy()
    editor_data["birth_date"] = editor_data["birth_date"].dt.strftime("%Y-%m-%d").fillna("")
    changed = st.data_editor(
        editor_data,
        use_container_width=True,
        hide_index=True,
        disabled=[col for col in editor_cols if col != "person_id"],
        key="person-id-editor",
    )
    edits = changed["person_id"].fillna("").astype(str).ne(editor_data["person_id"].fillna("").astype(str))
    if edits.any():
        con = open_db()
        for index in changed.index[edits]:
            row = data.loc[index]
            old_id = str(data.loc[index, "person_id"])
            new_id = str(changed.loc[index, "person_id"])
            con.execute(
                "INSERT INTO audit_v2(action,record_id,old_value,new_value) VALUES (?,?,?,?)",
                ("ID interno editado", f"{row['source']}:{row['source_row']}", old_id, new_id),
            )
            con.execute(
                "INSERT OR REPLACE INTO record_ids(source,source_row,person_id) VALUES (?,?,?)",
                (row["source"], int(row["source_row"]), new_id),
            )
            data.loc[index, "person_id"] = new_id
        con.commit()
        con.close()
        st.success("Cambios guardados en la base local; se reflejan al volver a cargar el análisis.")

    with st.expander("Bitácora de ajustes manuales"):
        con = open_db()
        audit = pd.read_sql_query("SELECT at,action,record_id,old_value,new_value FROM audit_v2 ORDER BY at DESC", con)
        con.close()
        st.dataframe(audit, use_container_width=True, hide_index=True)

with records_tab:
    st.subheader("Registros filtrados")
    st.caption("La exportación incluye los campos comunes, atributos originales, calidad, ID interno y ubicación de origen.")
    out = filtered.copy()
    out["birth_date"] = out["birth_date"].dt.strftime("%Y-%m-%d").fillna("")
    out["program_date"] = out["program_date"].dt.strftime("%Y-%m-%d").fillna("")
    display_cols = [
        "person_id", "source_person_id", "person_name", "birth_date", "program", "state", "municipality",
        "period", "program_date", "activity_type", "service", "quantity", "hair_length_cm", "source",
        "source_row", "quality", "source_attributes",
    ]
    st.dataframe(out[display_cols], use_container_width=True, hide_index=True, height=460)
    st.download_button(
        "Descargar registros filtrados (CSV)",
        out.drop(columns=["person_key"]).to_csv(index=False).encode("utf-8-sig"),
        "impacto_social_filtrado.csv",
        "text/csv",
        use_container_width=True,
    )
    summary = {
        "fecha_corte_actividad": cutoff_label if not filtered.empty else None,
        "programas": sorted(filtered["program"].dropna().unique().tolist()),
        "periodos": period_filter,
        "estados": state_filter,
        "municipios": municipality_filter,
        "tipos": type_filter,
        "servicios": service_filter,
        "filas": int(len(filtered)),
        "personas_unicas": int(filtered.loc[filtered["person_id"].ne(""), "person_id"].nunique()),
        "denominador": "IDs internos únicos en las filas que cumplen los filtros",
        "fuentes": sorted(filtered["source"].unique().tolist()),
        "alertas_en_seleccion": int(filtered["quality"].ne("OK").sum()),
    }
    st.download_button(
        "Descargar resumen de indicadores (JSON)",
        json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8"),
        "impacto_social_resumen.json",
        "application/json",
        use_container_width=True,
    )
