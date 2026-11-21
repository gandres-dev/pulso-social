import json, re, sqlite3, unicodedata, uuid
from datetime import date
from pathlib import Path
import pandas as pd
import streamlit as st

DB=Path(__file__).with_name("impacto.db")
FIELDS={"person_name":"Nombre","birth_date":"Nacimiento","municipality":"Municipio","program":"Programa","period":"Periodo","activity_type":"Tipo de actividad","service":"Servicio","quantity":"Cantidad"}
KINDS=["Servicio","Atención","Estudio","Entrega de insumos","Participación"]
def norm(x):
    if pd.isna(x): return ""
    s=unicodedata.normalize("NFKD",str(x).lower().strip())
    return re.sub(r"[^a-z0-9]","", "".join(c for c in s if not unicodedata.combining(c)))
def db():
    c=sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS people(id TEXT PRIMARY KEY,n TEXT,b TEXT,m TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS audit(at TEXT DEFAULT CURRENT_TIMESTAMP,record TEXT,old TEXT,new TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS record_ids(source TEXT,source_row INTEGER,person_id TEXT,PRIMARY KEY(source,source_row))")
    c.commit(); return c
def demo():
    cols1=["Nombre","Fecha nacimiento","Alcaldía","Programa","Mes","Tipo","Apoyo","Cantidad"]
    cols2=["Beneficiario","Nacimiento","Municipio","Programa social","Periodo","Actividad","Servicio","Unidades"]
    a=pd.DataFrame([["María López","1990-04-12","Iztapalapa","Bienestar","2026-10","Atención","Asesoría",1],["Jose Perez","1984-09-02","Neza","Bienestar","2026-10","Entrega de insumos","Despensa",1],["Ana García","2001-01-23","Iztapalapa","Jóvenes","2026-11","Participación","Taller",1]],columns=cols1)
    b=pd.DataFrame([["Maria Lopez","1990-04-12","Iztapalapa","Atención Comunitaria","2026-10","Estudio","Tamizaje",1],["Jose Perez","1984-09-02","Neza","Bienestar","2026-10","Entrega de insumos","Despensa",1],["Lucía Ramírez","1975-07-08","Tlalpan","Atención Comunitaria","2026-11","Servicio","Orientación",1]],columns=cols2)
    return {"fuente_a.csv":a,"fuente_b.xlsx":b}
def period(x):
    d=pd.to_datetime(x,errors="coerce",dayfirst=True)
    if pd.notna(d): return d.strftime("%Y-%m")
    m=re.search(r"(20\d{2})[-/]?(0?[1-9]|1[0-2])",str(x))
    return f"{m.group(1)}-{int(m.group(2)):02d}" if m else ""
def run_maps(frames):
    maps={}; tabs=st.tabs(list(frames))
    alias={"person_name":["nombre","beneficiario"],"birth_date":["nacimiento"],"municipality":["municipio","alcaldia"],"program":["programa"],"period":["periodo","mes"],"activity_type":["tipo","actividad"],"service":["servicio","apoyo"],"quantity":["cantidad","unidades"]}
    for tab,(name,df) in zip(tabs,frames.items()):
        with tab:
            st.dataframe(df.head(),use_container_width=True,hide_index=True); maps[name]={}; cols=["(sin mapear)"]+list(df.columns); grid=st.columns(2)
            for i,(key,label) in enumerate(FIELDS.items()):
                guess=next((c for c in df.columns if norm(c) in [norm(v) for v in alias[key]]),"(sin mapear)")
                with grid[i%2]: maps[name][key]=st.selectbox(label,cols,index=cols.index(guess),key=name+key)
    rows=[]
    for source,df in frames.items():
        for ix,r in df.iterrows():
            x={k:(r[maps[source][k]] if maps[source][k]!="(sin mapear)" else "") for k in FIELDS}
            mapped=[maps[source][k] for k in FIELDS if maps[source][k]!="(sin mapear)"]
            extras={str(k):(v.isoformat() if hasattr(v,"isoformat") else v.item() if hasattr(v,"item") else v) for k,v in r.items() if k not in mapped and pd.notna(v)}
            x["source_attributes"]=json.dumps(extras,ensure_ascii=False)
            hair_col=next((col for col in df.columns if "longituddetrenza" in norm(col)),None)
            x["hair_length_cm"]=pd.to_numeric(r[hair_col],errors="coerce") if hair_col else pd.NA
            x.update(source=source,source_row=ix+2); rows.append(x)
    d=pd.DataFrame(rows)
    for k in ["person_name","municipality","program","period","activity_type","service"]: d[k]=d[k].fillna("").astype(str).str.strip()
    d["birth_date"]=pd.to_datetime(d.birth_date,errors="coerce",dayfirst=True); d["period"]=d.period.map(period); d["quantity"]=pd.to_numeric(d.quantity,errors="coerce")
    d["quality"]="OK"
    for col,msg in [("person_name","falta nombre"),("municipality","falta municipio"),("program","falta programa"),("period","periodo inválido"),("activity_type","tipo faltante")]: d.loc[d[col].eq(""),"quality"]+=" · "+msg
    d.loc[d.quantity.isna()|d.quantity.le(0),"quality"]+=" · cantidad inválida"
    low_hair=d.program.map(norm).eq("melenasenmovimiento")&d.activity_type.map(norm).str.contains("donacion",na=False)&d.hair_length_cm.notna()&d.hair_length_cm.lt(30)
    d.loc[low_hair,"quality"]+=" · trenza menor a 30 cm"
    d["pkey"]=d.apply(lambda r:(norm(r.person_name),r.birth_date.strftime("%Y-%m-%d") if pd.notna(r.birth_date) else "",norm(r.municipality)),axis=1)
    dup=d.duplicated(["pkey","program","period","activity_type","service"],keep=False)&d.person_name.ne("")
    d.loc[dup,"quality"]+=" · posible evento duplicado"
    c=db(); people=c.execute("select id,n,b,m from people").fetchall(); ids=[]
    for row in d.itertuples():
        nk,bk,mk=row.pkey
        if not nk: ids.append(""); continue
        saved=c.execute("SELECT person_id FROM record_ids WHERE source=? AND source_row=?",(row.source,row.source_row)).fetchone()
        if saved:
            ids.append(saved[0]); continue
        old=next((p[0] for p in people if p[1:]==(nk,bk,mk)),None)
        maybe=next((p[0] for p in people if bk and mk and p[2]==bk and p[3]==mk and p[1]==nk),None)
        pid=old or maybe or "PER-"+uuid.uuid4().hex[:10].upper()
        if not old and not maybe: c.execute("insert into people values(?,?,?,?)",(pid,nk,bk,mk)); people.append((pid,nk,bk,mk))
        ids.append(pid)
        c.execute("INSERT OR REPLACE INTO record_ids VALUES (?,?,?)",(row.source,row.source_row,pid))
    c.commit(); c.close(); d["person_id"]=ids
    return d
st.set_page_config(page_title="Impacto social",page_icon="🌱",layout="wide")
st.title("🌱 Consolidador de impacto social")
st.caption("Importa y armoniza fuentes, revisa calidad y explora resultados con trazabilidad.")
with st.sidebar:
    demo_button=st.button("Cargar demo con 2 fuentes")
    files=st.file_uploader("CSV o Excel",type=["csv","xlsx","xls"],accept_multiple_files=True)
if demo_button: st.session_state.frames=demo()
if files:
    loaded={}
    for f in files:
        try: loaded[f.name]=pd.read_csv(f) if f.name.endswith(".csv") else pd.read_excel(f)
        except Exception as e: st.error(f"Error al leer {f.name}: {e}")
    st.session_state.frames=loaded
frames=st.session_state.get("frames",{})
if not frames:
    st.info("Carga tus fuentes o activa la demo.")
    st.stop()
st.subheader("1 · Mapeo de columnas")
st.caption("Conservamos archivo y fila de origen.")
d=run_maps(frames)
if st.button("Validar y generar IDs",type="primary") or "data" not in st.session_state: st.session_state.data=d
d=st.session_state.data.copy()
st.subheader("2 · Calidad y personas")
a,b,c,e=st.columns(4)
a.metric("Registros",len(d)); b.metric("Personas únicas",d.loc[d.person_id.ne(""),"person_id"].nunique()); c.metric("Filas por revisar",int(d.quality.ne("OK").sum())); e.metric("Filas marcadas como duplicado",int(d.quality.str.contains("posible evento duplicado").sum()))
st.caption("ID por nombre normalizado + nacimiento + municipio. Los eventos repetidos se marcan, no se borran automáticamente.")
v=d.copy(); v.birth_date=v.birth_date.dt.strftime("%Y-%m-%d").fillna("")
cols=["person_id","person_name","birth_date","municipality","program","period","activity_type","service","quantity","hair_length_cm","source","source_row","quality"]
edit=st.data_editor(v[cols],disabled=[x for x in cols if x!="person_id"],use_container_width=True,hide_index=True)
if not edit.equals(v[cols]):
    c=db()
    for _,r in edit.iterrows():
        old=d.loc[d.source.eq(r.source)&d.source_row.eq(r.source_row),"person_id"].iloc[0]
        if old!=r.person_id:
            c.execute("insert into audit(record,old,new) values(?,?,?)",(f"{r.source}:{r.source_row}",old,r.person_id))
            c.execute("INSERT OR REPLACE INTO record_ids VALUES (?,?,?)",(r.source,int(r.source_row),r.person_id))
    c.commit(); c.close(); st.info("Cambio registrado en bitácora.")
st.subheader("3 · Indicadores")
f1,f2,f3,f4=st.columns(4)
fields=["program","period","municipality","activity_type"]
options=[sorted(d[x][d[x].ne("")].unique()) for x in fields]
selected=[f1.multiselect("Programa",options[0],default=options[0]),f2.multiselect("Periodo",options[1],default=options[1]),f3.multiselect("Municipio",options[2],default=options[2]),f4.multiselect("Tipo",options[3],default=options[3])]
q=d[d.program.isin(selected[0])&d.period.isin(selected[1])&d.municipality.isin(selected[2])&d.activity_type.isin(selected[3])]
vals=[q.loc[q.activity_type.eq(t),"quantity"].sum() for t in ["Atención","Servicio","Participación"]]
for col,label,value in zip(st.columns(4),["Personas únicas","Atenciones","Servicios","Participaciones"],[q.loc[q.person_id.ne(""),"person_id"].nunique(),*vals]): col.metric(label,int(value) if pd.notna(value) else 0)
st.caption(f"Corte {date.today().isoformat()} · Denominador: IDs únicos del filtro · Fuentes: {', '.join(sorted(q.source.unique()))}")
counts=q.groupby("activity_type").agg(registros=("person_id","size"),personas=("person_id","nunique"),unidades=("quantity","sum")).reset_index()
st.bar_chart(counts.set_index("activity_type")[["registros","personas","unidades"]]); st.dataframe(counts,hide_index=True,use_container_width=True)
st.subheader("4 · Exportación")
out=q.copy(); out.birth_date=out.birth_date.dt.strftime("%Y-%m-%d")
st.download_button("CSV consolidado con trazabilidad",out.drop(columns="pkey").to_csv(index=False).encode("utf-8-sig"),"impacto_consolidado.csv","text/csv")
summary={"corte":date.today().isoformat(),"filtros":dict(zip(fields,selected)),"filas":len(q),"personas_unicas":int(q.loc[q.person_id.ne(""),"person_id"].nunique()),"fuentes":sorted(q.source.unique().tolist())}
st.download_button("Resumen JSON",json.dumps(summary,ensure_ascii=False,indent=2).encode(),"resumen.json","application/json")
with st.expander("Bitácora de IDs editados"):
    c=db(); log=pd.read_sql_query("select at,record,old,new from audit order by at desc",c); c.close(); st.dataframe(log,hide_index=True,use_container_width=True)
