import streamlit as st
import pandas as pd
import requests
import io
import sqlite3
import time
from datetime import datetime, timedelta

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Monitor ODC - RIOMARKET", layout="wide")

# --- ESTILOS CSS (Blanco, Verde, Profundidad) ---
st.markdown("""
<style>
    .rotating-card {
        background-color: #FFFFFF;
        border: 6px solid #28a745;
        border-radius: 20px;
        padding: 40px;
        text-align: center;
        box-shadow: 10px 10px 0px #1e7e34; /* Efecto de profundidad */
        margin: 20px auto;
        max-width: 800px;
        transition: all 0.5s ease;
    }
    .order-label { color: #28a745; font-size: 1.5rem; font-weight: bold; margin-bottom: 0; }
    .order-number { font-size: 8rem; font-weight: 900; color: #1e7e34; line-height: 1; margin: 10px 0; }
    .order-provider { font-size: 2.5rem; font-weight: bold; color: #333; text-transform: uppercase; }
    .order-buyer { font-size: 1.2rem; color: #666; margin-top: 15px; }
    
    /* Optimización de Sidebar */
    section[data-testid="stSidebar"] { background-color: #f8f9fa; border-right: 1px solid #ddd; }
</style>
""", unsafe_allow_html=True)

# --- 1. BASE DE DATOS Y LÓGICA ---
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

def cargar_semana(fecha_consulta):
    conn = sqlite3.connect('calendario.db')
    f_str = str(fecha_consulta)
    df = pd.read_sql_query("SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?", conn, params=(f_str,))
    if not df.empty:
        res = dict(zip(df['dia_semana'], df['proveedores'].apply(lambda x: x.split(',') if x else [])))
        conn.close()
        return res
    # Herencia
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(fecha_semana) FROM calendario_historico WHERE fecha_semana < ?", (f_str,))
    ultima = cursor.fetchone()
    if ultima and ultima[0]:
        df_h = pd.read_sql_query("SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?", conn, params=(ultima[0],))
        conn.close()
        return dict(zip(df_h['dia_semana'], df_h['proveedores'].apply(lambda x: x.split(',') if x else [])))
    conn.close()
    return {d: [] for d in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]}

def guardar_calendario(fecha, cal_dict):
    conn = sqlite3.connect('calendario.db')
    for dia, provs in cal_dict.items():
        p_str = ",".join([p.strip().upper() for p in provs if p.strip()])
        conn.execute("INSERT OR REPLACE INTO calendario_historico (fecha_semana, dia_semana, proveedores) VALUES (?, ?, ?)", (str(fecha), dia, p_str))
    conn.commit()
    conn.close()

init_db()

# --- 2. ESTADO DE SESIÓN ---
if 'fecha_referencia' not in st.session_state:
    hoy = datetime.now()
    st.session_state.fecha_referencia = (hoy - timedelta(days=hoy.weekday())).date()
if 'indice_rotacion' not in st.session_state:
    st.session_state.indice_rotacion = 0

# --- 3. SIDEBAR OPTIMIZADO ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3043/3043888.png", width=80) # Icono decorativo
    st.title("Configuración")
    
    with st.expander("📅 Planificación Semanal", expanded=True):
        dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        dia_sel = st.selectbox("Día:", dias)
        cal_data = cargar_semana(st.session_state.fecha_referencia)
        txt_provs = st.text_area("Proveedores:", value=", ".join(cal_data.get(dia_sel, [])))
        if st.button("💾 Guardar Semana"):
            cal_data[dia_sel] = [p.strip().upper() for p in txt_provs.split(",") if p.strip()]
            guardar_calendario(st.session_state.fecha_referencia, cal_data)
            st.success("Guardado")
            st.rerun()

    with st.expander("👤 Maestro de Compradores"):
        p_new = st.text_input("Proveedor:")
        c_new = st.text_input("Comprador:")
        if st.button("➕ Registrar"):
            if p_new and c_new:
                conn = sqlite3.connect('calendario.db')
                conn.execute("INSERT INTO proveedores_maestro (nombre, comprador_habitual) VALUES (?, ?)", (p_new.upper(), c_new.upper()))
                conn.commit(); conn.close()
                st.rerun()
        
        if st.checkbox("🔍 Gestionar Registros"):
            conn = sqlite3.connect('calendario.db')
            df_m = pd.read_sql_query("SELECT * FROM proveedores_maestro", conn)
            conn.close()
            st.data_editor(df_m, hide_index=True, key="edit_m")

    with st.expander("⚠️ Zona de Peligro"):
        if st.button("BORRAR TODO"):
            conn = sqlite3.connect('calendario.db')
            conn.execute("DROP TABLE IF EXISTS calendario_historico")
            conn.execute("DROP TABLE IF EXISTS proveedores_maestro")
            conn.commit(); conn.close()
            init_db()
            st.rerun()

# --- 4. ÁREA PRINCIPAL ---
st.title("📅 Monitor de Órdenes de Compra")

col1, col2, col3 = st.columns([1,2,1])
with col1: 
    if st.button("⬅️ Semana Anterior"): 
        st.session_state.fecha_referencia -= timedelta(days=7); st.rerun()
with col3: 
    if st.button("Siguiente Semana ➡️"): 
        st.session_state.fecha_referencia += timedelta(days=7); st.rerun()

st.info(f"Visualizando: {st.session_state.fecha_referencia} | Hoy: {datetime.now().strftime('%A, %d %B')}")

# --- 5. LÓGICA DE ROTACIÓN DE ÓRDENES ---
st.divider()
dia_hoy = dias[datetime.now().weekday()]
provs_hoy = cal_data.get(dia_hoy, [])

if not provs_hoy:
    st.warning(f"No hay proveedores programados para hoy {dia_hoy}.")
else:
    url = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/ODC_alerta.xlsx"
    try:
        res = requests.get(url)
        df_raw = pd.read_excel(io.BytesIO(res.content))
        df_raw.columns = df_raw.columns.str.strip()
        df_raw = df_raw.rename(columns={'Creado por': 'Comprador'})
        
        # Validar autorizados
        conn = sqlite3.connect('calendario.db')
        df_aut = pd.read_sql_query("SELECT nombre, comprador_habitual FROM proveedores_maestro", conn)
        conn.close()
        
        df_aut['key'] = df_aut['nombre'].str.upper() + "|" + df_aut['comprador_habitual'].str.upper()
        set_aut = set(df_aut['key'].tolist())

        def validar(row):
            p, c = str(row['Proveedor']).upper().strip(), str(row['Comprador']).upper().strip()
            # Si el proveedor está en la lista de hoy y el par P|C está autorizado
            match_hoy = any(px in p for px in provs_hoy)
            return match_hoy and f"{p}|{c}" in set_aut

        df_f = df_raw[df_raw.apply(validar, axis=1)].sort_values('Número de orden').copy()

        if not df_f.empty:
            ordenes = df_f.to_dict('records')
            # Control de índice circular
            if st.session_state.indice_rotacion >= len(ordenes):
                st.session_state.indice_rotacion = 0
            
            ord_actual = ordenes[st.session_state.indice_rotacion]
            
            # MOSTRAR ORDEN (Estilo Carousel)
            st.markdown(f"""
                <div class="rotating-card">
                    <div class="order-label">ORDEN DE COMPRA</div>
                    <div class="order-number">{str(ord_actual['Número de orden'])[-4:]}</div>
                    <div class="order-provider">{ord_actual['Proveedor']}</div>
                    <div class="order-buyer">👤 Comprador: {ord_actual['Comprador']}</div>
                    <div style="margin-top:20px; color:#aaa; font-size:0.8rem;">
                        Mostrando {st.session_state.indice_rotacion + 1} de {len(ordenes)} órdenes validadas
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            # Lógica de rotación automática
            st.session_state.indice_rotacion += 1
            time.sleep(5) # Espera 5 segundos
            st.rerun() # Recarga para mostrar la siguiente
            
        else:
            st.info(f"✅ No hay órdenes pendientes para {dia_hoy}.")
    except Exception as e:
        st.error(f"Error en consulta: {e}")
