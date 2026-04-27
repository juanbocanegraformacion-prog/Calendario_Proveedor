import streamlit as st
import pandas as pd
import requests
import io
import sqlite3
from datetime import datetime, timedelta

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Monitor ODC - RIOMARKET", layout="wide")

# --- VARIABLES GLOBALES ---
dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

# --- ESTILOS CSS (SISTEMA DE COLA) ---
st.markdown("""
<style>
    .main-order-container {
        background-color: #FFC107;
        color: black;
        border-radius: 15px;
        padding: 30px;
        text-align: center;
        border: 5px solid #E67E22;
        margin-bottom: 20px;
    }
    .main-order-title { font-size: 1.8rem; font-weight: bold; }
    .main-order-number { font-size: 7rem; font-weight: 900; line-height: 1; margin: 10px 0; }
    .main-order-info { font-size: 1.4rem; font-weight: bold; }
    
    .queue-card {
        background-color: #262730;
        color: white;
        border-radius: 10px;
        padding: 12px;
        margin-bottom: 10px;
        border-left: 8px solid #FFC107;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .queue-number { font-size: 1.8rem; font-weight: bold; color: #FFC107; }
    .queue-details { text-align: right; font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)

# --- 1. BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS proveedores_maestro 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, comprador_habitual TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS calendario_historico 
                      (id INTEGER PRIMARY KEY, fecha_semana TEXT, dia_semana TEXT, proveedores TEXT)''')
    cursor.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_fecha_dia ON calendario_historico (fecha_semana, dia_semana)''')
    conn.commit()
    conn.close()

init_db()

def cargar_semana(fecha_consulta):
    conn = sqlite3.connect('calendario.db')
    fecha_str = str(fecha_consulta)
    df = pd.read_sql_query("SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?", conn, params=(fecha_str,))
    
    if not df.empty:
        res = dict(zip(df['dia_semana'], df['proveedores'].apply(lambda x: x.split(',') if x else [])))
        conn.close()
        return res
    
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(fecha_semana) FROM calendario_historico WHERE fecha_semana < ?", (fecha_str,))
    ultima = cursor.fetchone()
    if ultima and ultima[0]:
        df_h = pd.read_sql_query("SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?", conn, params=(ultima[0],))
        conn.close()
        return dict(zip(df_h['dia_semana'], df_h['proveedores'].apply(lambda x: x.split(',') if x else [])))
    
    conn.close()
    return {d: [] for d in dias_semana}

def guardar_calendario(fecha, calendario_dict):
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    for dia, lista_provs in calendario_dict.items():
        provs_str = ",".join([p.strip().upper() for p in lista_provs if p.strip()])
        cursor.execute("INSERT OR REPLACE INTO calendario_historico (fecha_semana, dia_semana, proveedores) VALUES (?, ?, ?)", (str(fecha), dia, provs_str))
    conn.commit()
    conn.close()

def obtener_compradores_autorizados():
    conn = sqlite3.connect('calendario.db')
    df = pd.read_sql_query("SELECT id, nombre, comprador_habitual FROM proveedores_maestro", conn)
    conn.close()
    return df

# --- 2. GESTIÓN DE FECHAS ---
if 'fecha_referencia' not in st.session_state:
    hoy = datetime.now()
    st.session_state.fecha_referencia = (hoy - timedelta(days=hoy.weekday())).date()

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Configuración")
    dia_edit = st.selectbox("Día a editar:", dias_semana)
    cal_actual = cargar_semana(st.session_state.fecha_referencia)
    provs_input = st.text_area("Proveedores (sep. por coma):", value=", ".join(cal_actual.get(dia_edit, [])))

    if st.button("💾 Guardar Planificación"):
        cal_actual[dia_edit] = [p.strip().upper() for p in provs_input.split(",") if p.strip()]
        guardar_calendario(st.session_state.fecha_referencia, cal_actual)
        st.rerun()

    st.divider()
    st.subheader("👤 Registro Maestro")
    np, nc = st.text_input("Proveedor:"), st.text_input("Comprador:")
    if st.button("➕ Registrar"):
        if np and nc:
            conn = sqlite3.connect('calendario.db')
            conn.execute("INSERT INTO proveedores_maestro (nombre, comprador_habitual) VALUES (?, ?)", (np.upper(), nc.upper()))
            conn.commit()
            conn.close()
            st.rerun()

# --- 4. ÁREA PRINCIPAL ---
st.title("📅 Monitor de Órdenes de Compra")

c1, c2, c3 = st.columns([1,2,1])
with c1:
    if st.button("⬅️ Anterior"):
        st.session_state.fecha_referencia -= timedelta(days=7); st.rerun()
with c3:
    if st.button("Siguiente ➡️"):
        st.session_state.fecha_referencia += timedelta(days=7); st.rerun()

st.markdown(f"### Semana: {st.session_state.fecha_referencia}")
cal_data = cargar_semana(st.session_state.fecha_referencia)
df_visual = pd.DataFrame.from_dict(cal_data, orient='index').transpose().fillna("-")
st.dataframe(df_visual, use_container_width=True, hide_index=True)

st.divider()

# --- 5. MONITOREO (SISTEMA DE COLA) ---
st.subheader("🤖 Monitoreo en Tiempo Real")
dia_hoy_es = dias_semana[datetime.now().weekday()]
provs_hoy = cal_data.get(dia_hoy_es, [])

if not provs_hoy:
    st.info(f"No hay proveedores hoy ({dia_hoy_es}).")
else:
    url = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/ODC_alerta.xlsx"
    try:
        res = requests.get(url)
        df_raw = pd.read_excel(io.BytesIO(res.content))
        df_raw.columns = df_raw.columns.str.strip()
        df_raw = df_raw.rename(columns={'Creado por': 'Comprador'})
        
        df_aut = obtener_compradores_autorizados()
        df_aut['key'] = df_aut['nombre'].str.upper().str.strip() + "|" + df_aut['comprador_habitual'].str.upper().str.strip()
        set_aut = set(df_aut['key'].tolist())

        def validar(row):
            p, c = str(row['Proveedor']).upper().strip(), str(row['Comprador']).upper().strip()
            if not any(px in p for px in provs_hoy): return False
            return f"{p}|{c}" in set_aut

        df_f = df_raw[df_raw.apply(validar, axis=1)].copy()

        if not df_f.empty:
            ordenes = df_f.to_dict('records')
            ultima = ordenes[-1]
            anteriores = ordenes[:-1][::-1]

            col_l, col_r = st.columns([2, 1])
            with col_l:
                st.markdown(f"""<div class="main-order-container">
                    <div class="main-order-title">TURNO ACTUAL</div>
                    <div class="main-order-number">{str(ultima['Número de orden'])[-4:]}</div>
                    <div class="main-order-info">{ultima['Proveedor']}</div>
                    <div style="color: #333;">Comprador: {ultima['Comprador']}</div>
                </div>""", unsafe_allow_html=True)
            with col_r:
                st.markdown("<h4 style='text-align: center;'>EN ESPERA</h4>", unsafe_allow_html=True)
                for o in anteriores[:4]:
                    st.markdown(f"""<div class="queue-card">
                        <div class="queue-number">#{str(o['Número de orden'])[-4:]}</div>
                        <div class="queue-details"><b>{str(o['Proveedor'])[:15]}...</b><br>{o['Comprador']}</div>
                    </div>""", unsafe_allow_html=True)
        else:
            st.info("Buscando órdenes validadas...")
    except Exception as e:
        st.error(f"Error en la sincronización: {e}")
