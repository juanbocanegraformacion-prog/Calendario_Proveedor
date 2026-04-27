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

# --- LÓGICA DE HERENCIA ---
def cargar_semana(fecha_consulta):
    conn = sqlite3.connect('calendario.db')
    fecha_str = str(fecha_consulta)
    
    # 1. Intentar cargar la semana exacta
    df = pd.read_sql_query("SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?", 
                           conn, params=(fecha_str,))
    
    if not df.empty:
        res = dict(zip(df['dia_semana'], df['proveedores'].apply(lambda x: x.split(',') if x else [])))
        conn.close()
        return res
    
    # 2. HERENCIA: Buscar la última fecha grabada en el pasado
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(fecha_semana) FROM calendario_historico WHERE fecha_semana < ?", (fecha_str,))
    ultima_fecha_result = cursor.fetchone()
    
    if ultima_fecha_result and ultima_fecha_result[0]:
        ultima_fecha = ultima_fecha_result[0]
        df_heredado = pd.read_sql_query("SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?", 
                                        conn, params=(ultima_fecha,))
        conn.close()
        return dict(zip(df_heredado['dia_semana'], df_heredado['proveedores'].apply(lambda x: x.split(',') if x else [])))
    
    conn.close()
    return {d: [] for d in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]}

def guardar_calendario(fecha, calendario_dict):
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    fecha_str = str(fecha)
    for dia, lista_provs in calendario_dict.items():
        provs_str = ",".join([p.strip().upper() for p in lista_provs if p.strip()])
        cursor.execute('''INSERT OR REPLACE INTO calendario_historico (fecha_semana, dia_semana, proveedores) 
                          VALUES (?, ?, ?)''', (fecha_str, dia, provs_str))
    conn.commit()
    conn.close()

def registrar_comprador(proveedor, comprador):
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    p_up, c_up = proveedor.strip().upper(), comprador.strip().upper()
    cursor.execute("SELECT 1 FROM proveedores_maestro WHERE nombre = ? AND comprador_habitual = ?", (p_up, c_up))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO proveedores_maestro (nombre, comprador_habitual) VALUES (?, ?)", (p_up, c_up))
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
    dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    dia_edit = st.selectbox("Día a editar:", dias_semana)
    
    datos_actuales = cargar_semana(st.session_state.fecha_referencia)
    
    provs_input = st.text_area("Proveedores para este día:", 
                               value=", ".join(datos_actuales.get(dia_edit, [])))

    if st.button("💾 Guardar Planificación"):
        datos_actuales[dia_edit] = [p.strip().upper() for p in provs_input.split(",") if p.strip()]
        guardar_calendario(st.session_state.fecha_referencia, datos_actuales)
        st.success(f"Configuración guardada para la semana {st.session_state.fecha_referencia}")
        st.rerun()

    st.divider()
    st.subheader("👤 Registro Maestro")
    new_p = st.text_input("Proveedor:")
    new_c = st.text_input("Comprador:")
    if st.button("➕ Registrar"):
        if new_p and new_c:
            registrar_comprador(new_p, new_c)
            st.rerun()

    if st.checkbox("🔍 Gestionar Registros"):
        df_m = obtener_compradores_autorizados()
        if not df_m.empty:
            opciones_borrar = {row['id']: f"{row['nombre']} - ({row['comprador_habitual']})" for _, row in df_m.iterrows()}
            id_del = st.selectbox("Eliminar:", options=list(opciones_borrar.keys()), format_func=lambda x: opciones_borrar[x])
            if st.button("🗑️ Eliminar"):
                conn = sqlite3.connect('calendario.db')
                conn.execute("DELETE FROM proveedores_maestro WHERE id = ?", (id_del,))
                conn.commit()
                conn.close()
                st.rerun()

# --- 4. ÁREA PRINCIPAL ---
st.title("📅 Monitor de Órdenes de Compra")

c1, c2, c3 = st.columns([1, 2, 1])
with c1:
    if st.button("⬅️ Anterior"):
        st.session_state.fecha_referencia -= timedelta(days=7)
        st.rerun()
with c3:
    if st.button("Siguiente ➡️"):
        st.session_state.fecha_referencia += timedelta(days=7)
        st.rerun()

st.subheader(f"Planificación Semana: {st.session_state.fecha_referencia}")

plan_visual = cargar_semana(st.session_state.fecha_referencia)
df_visual = pd.DataFrame.from_dict(plan_visual, orient='index').transpose().fillna("-")
st.dataframe(df_visual, use_container_width=True, hide_index=True)

st.divider()

# --- 5. MONITOREO (CORREGIDO ERROR DE STRIP) ---
st.subheader("🤖 Monitoreo en Tiempo Real")
dia_hoy_idx = datetime.now().weekday()
dia_hoy_es = dias_semana[dia_hoy_idx]
provs_hoy = [p for p in plan_visual.get(dia_hoy_es, []) if p and p != "-"]

if not provs_hoy:
    st.info(f"No hay proveedores programados para hoy ({dia_hoy_es}).")
else:
    url_excel = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/ODC_alerta.xlsx"
    try:
        res = requests.get(url_excel)
        df_raw = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
        df_raw.columns = df_raw.columns.str.strip()
        df_raw = df_raw.rename(columns={'Creado por': 'Comprador'})
        
        df_aut = obtener_compradores_autorizados()
        
        # CORRECCIÓN AQUÍ: Uso de .str antes de upper() y strip()
        df_aut['key'] = (
            df_aut['nombre'].str.upper().str.strip() + 
            "|" + 
            df_aut['comprador_habitual'].str.upper().str.strip()
        )
        set_aut = set(df_aut['key'].tolist())

        def validar(row):
            p_ex = str(row['Proveedor']).upper().strip()
            c_ex = str(row['Comprador']).upper().strip()
            if not any(p in p_ex for p in provs_hoy): return False
            return f"{p_ex}|{c_ex}" in set_aut

        df_filtrado = df_raw[df_raw.apply(validar, axis=1)].copy()
        if not df_filtrado.empty:
            st.success(f"Órdenes validadas para {dia_hoy_es}:")
            st.dataframe(df_filtrado[['Número de orden', 'Proveedor', 'Estatus', 'Comprador']], 
                         use_container_width=True, hide_index=True)
        else:
            st.info(f"✅ Sin órdenes pendientes para los proveedores de hoy.")
    except Exception as e:
        st.error(f"Error: {e}")
