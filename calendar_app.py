import streamlit as st
import pandas as pd
import requests
import io
import sqlite3
from datetime import datetime, timedelta

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Monitor ODC - RIOMARKET", layout="wide")

# --- 1. PERSISTENCIA Y BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS proveedores_maestro 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       nombre TEXT, 
                       comprador_habitual TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS calendario_historico 
                      (id INTEGER PRIMARY KEY, fecha_semana TEXT, dia_semana TEXT, proveedores TEXT)''')
    cursor.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_fecha_dia 
                      ON calendario_historico (fecha_semana, dia_semana)''')
    conn.commit()
    conn.close()

init_db()

# --- LÓGICA DE HERENCIA DINÁMICA (LA CLAVE) ---
def cargar_semana(fecha_consulta):
    conn = sqlite3.connect('calendario.db')
    fecha_str = str(fecha_consulta)
    
    # 1. Intentar cargar la semana exacta
    df = pd.read_sql_query("SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?", 
                           conn, params=(fecha_str,))
    
    if not df.empty:
        conn.close()
        return dict(zip(df['dia_semana'], df['proveedores'].apply(lambda x: x.split(',') if x else [])))
    
    # 2. Si la semana está vacía, buscamos la FECHA MÁS RECIENTE grabada en el pasado
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(fecha_semana) FROM calendario_historico WHERE fecha_semana < ?", (fecha_str,))
    ultima_fecha_disponible = cursor.fetchone()[0]
    
    if ultima_fecha_disponible:
        df_heredado = pd.read_sql_query("SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?", 
                                        conn, params=(ultima_fecha_disponible,))
        conn.close()
        if not df_heredado.empty:
            return dict(zip(df_heredado['dia_semana'], df_heredado['proveedores'].apply(lambda x: x.split(',') if x else [])))
    
    conn.close()
    # 3. Si no hay absolutamente nada en la DB, devolver estructura vacía
    return {d: [] for d in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]}

def guardar_calendario(fecha, calendario_dict):
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    for dia, lista_provs in calendario_dict.items():
        provs_str = ",".join([p.strip().upper() for p in lista_provs if p.strip()])
        cursor.execute('''INSERT OR REPLACE INTO calendario_historico (fecha_semana, dia_semana, proveedores) 
                          VALUES (?, ?, ?)''', (str(fecha), dia, provs_str))
    conn.commit()
    conn.close()

# --- LÓGICA DE COMPRADORES ---
def obtener_compradores_autorizados():
    conn = sqlite3.connect('calendario.db')
    df = pd.read_sql_query("SELECT id, nombre, comprador_habitual FROM proveedores_maestro", conn)
    conn.close()
    return df

# --- 2. GESTIÓN DE ESTADO Y FECHAS ---
if 'fecha_referencia' not in st.session_state:
    hoy = datetime.now()
    st.session_state.fecha_referencia = (hoy - timedelta(days=hoy.weekday())).date()

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Configuración")
    
    st.subheader("📅 Planificación")
    dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    dia_edit = st.selectbox("Día a editar:", dias_semana)
    
    # Cargamos la planificación (aquí se aplica la herencia si la semana es nueva)
    cal_actual = cargar_semana(st.session_state.fecha_referencia)
    
    provs_input = st.text_area("Proveedores (sep. por coma):", 
                               value=", ".join(cal_actual.get(dia_edit, [])))

    if st.button("💾 Guardar Semana Actual"):
        cal_actual[dia_edit] = [p.strip().upper() for p in provs_input.split(",") if p.strip()]
        guardar_calendario(st.session_state.fecha_referencia, cal_actual)
        st.success(f"Configuración fijada para la semana {st.session_state.fecha_referencia}")
        st.rerun()

# --- 4. CUERPO PRINCIPAL ---
st.title("📅 Monitor de Órdenes de Compra")

col1, col2, col3 = st.columns([1,2,1])
with col1:
    if st.button("⬅️ Semana Anterior"):
        st.session_state.fecha_referencia -= timedelta(days=7)
        st.rerun()
with col3:
    if st.button("Siguiente Semana ➡️"):
        st.session_state.fecha_referencia += timedelta(days=7)
        st.rerun()

st.markdown(f"### Visualizando: Semana del {st.session_state.fecha_referencia}")

# Cargamos los datos que se mostrarán en la tabla
cal_data_display = cargar_semana(st.session_state.fecha_referencia)
df_display = pd.DataFrame.from_dict(cal_data_display, orient='index').transpose().fillna("-")
st.dataframe(df_display, use_container_width=True, hide_index=True)

st.divider()

# --- 5. MONITOREO EN TIEMPO REAL ---
st.subheader("🤖 Monitoreo en Tiempo Real")

# Determinamos el día de hoy según el sistema
dia_hoy_idx = datetime.now().weekday()
dia_hoy_nombre = dias_semana[dia_hoy_idx]

# IMPORTANTE: El monitoreo debe usar la fecha real de hoy para buscar proveedores, 
# pero si estamos navegando en el futuro, usaremos los proveedores de la semana que estamos viendo.
provs_hoy = [p for p in cal_data_display.get(dia_hoy_nombre, []) if p and p != "-"]

if not provs_hoy:
    st.warning(f"No hay proveedores programados para hoy ({dia_hoy_nombre}) en la planificación seleccionada.")
else:
    st.success(f"Proveedores activos hoy ({dia_hoy_nombre}): {', '.join(provs_hoy)}")
    
    # Lógica de sincronización con Excel...
    url_excel = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/odc_alerta.xlsx"
    try:
        res = requests.get(url_excel)
        df_raw = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
        df_raw.columns = df_raw.columns.str.strip()
        df_raw = df_raw.rename(columns={'Creado por': 'Comprador'})
        
        df_aut = obtener_compradores_autorizados()
        df_aut['key'] = df_aut['nombre'].str.upper().strip() + "|" + df_aut['comprador_habitual'].str.upper().strip()
        set_aut = set(df_aut['key'].tolist())

        def validar(row):
            p_ex = str(row['Proveedor']).upper().strip()
            c_ex = str(row['Comprador']).upper().strip()
            # Valida si el proveedor del Excel coincide con la lista planificada (heredada o actual)
            if not any(p in p_ex for p in provs_hoy): return False
            return f"{p_ex}|{c_ex}" in set_aut

        df_filtrado = df_raw[df_raw.apply(validar, axis=1)].copy()

        if not df_filtrado.empty:
            st.dataframe(df_filtrado[['Número de orden', 'Proveedor', 'Estatus', 'Comprador']], use_container_width=True)
        else:
            st.info("No se encontraron órdenes para los proveedores planificados.")
    except Exception as e:
        st.error(f"Error de conexión: {e}")
