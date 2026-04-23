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

def forzar_reset_maestro():
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS proveedores_maestro")
    conn.commit()
    conn.close()
    st.cache_data.clear()

init_db()

# --- LÓGICA DE CARGA CON HERENCIA REFORZADA ---
def cargar_semana(fecha_solicitada):
    conn = sqlite3.connect('calendario.db')
    fecha_str = str(fecha_solicitada)
    
    # 1. Intentar cargar la semana exacta
    df = pd.read_sql_query("SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?", 
                           conn, params=(fecha_str,))
    
    if not df.empty:
        conn.close()
        return dict(zip(df['dia_semana'], df['proveedores'].apply(lambda x: x.split(',') if x else [])))
    
    # 2. Si está vacía, buscar la ÚLTIMA semana que tenga CUALQUIER dato grabado
    # Buscamos la fecha máxima grabada que sea menor a la solicitada
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(fecha_semana) FROM calendario_historico WHERE fecha_semana < ?", (fecha_str,))
    ultima_fecha = cursor.fetchone()[0]
    
    if ultima_fecha:
        df_heredado = pd.read_sql_query("SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?", 
                                        conn, params=(ultima_fecha,))
        conn.close()
        if not df_heredado.empty:
            return dict(zip(df_heredado['dia_semana'], df_heredado['proveedores'].apply(lambda x: x.split(',') if x else [])))
    
    conn.close()
    return {d: [] for d in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]}

def guardar_calendario(fecha, calendario_dict):
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    for dia, lista_provs in calendario_dict.items():
        provs_str = ",".join(lista_provs)
        cursor.execute('''INSERT OR REPLACE INTO calendario_historico (fecha_semana, dia_semana, proveedores) 
                          VALUES (?, ?, ?)''', (str(fecha), dia, provs_str))
    conn.commit()
    conn.close()

def registrar_comprador(proveedor, comprador):
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    p_up, c_up = proveedor.strip().upper(), comprador.strip().upper()
    try:
        cursor.execute("SELECT 1 FROM proveedores_maestro WHERE nombre = ? AND comprador_habitual = ?", (p_up, c_up))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO proveedores_maestro (nombre, comprador_habitual) VALUES (?, ?)", (p_up, c_up))
            conn.commit()
        conn.close()
        return True
    except:
        conn.close()
        return False

def eliminar_comprador(id_registro):
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM proveedores_maestro WHERE id = ?", (id_registro,))
    conn.commit()
    conn.close()

def obtener_compradores_autorizados():
    conn = sqlite3.connect('calendario.db')
    df = pd.read_sql_query("SELECT id, nombre, comprador_habitual FROM proveedores_maestro", conn)
    conn.close()
    return df

# --- 2. LÓGICA DE FECHAS ---
if 'fecha_referencia' not in st.session_state:
    hoy = datetime.now()
    st.session_state.fecha_referencia = (hoy - timedelta(days=hoy.weekday())).date()

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Panel de Configuración")
    
    with st.expander("🛠️ Herramientas de Sistema"):
        if st.button("Reparar Base de Datos"):
            forzar_reset_maestro()
            st.rerun()

    st.divider()
    st.subheader("📅 Planificación Semanal")
    dias_list = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    dia_edit = st.selectbox("Día a editar:", dias_list)
    
    # Cargar datos con la nueva herencia
    cal_actual = cargar_semana(st.session_state.fecha_referencia)
    
    provs_input = st.text_area("Proveedores para el día seleccionado:", 
                               value=", ".join(cal_actual.get(dia_edit, [])))

    if st.button("💾 Guardar Planificación"):
        # Actualizamos el diccionario local
        cal_actual[dia_edit] = [p.strip().upper() for p in provs_input.split(",") if p.strip()]
        # Guardamos en DB para la fecha de referencia actual
        guardar_calendario(st.session_state.fecha_referencia, cal_actual)
        st.success(f"Guardado para la semana del {st.session_state.fecha_referencia}")
        st.rerun()

    st.divider()
    st.subheader("👤 Compradores")
    new_p = st.text_input("Proveedor:")
    new_c = st.text_input("Comprador:")
    if st.button("➕ Registrar Comprador"):
        if new_p and new_c:
            registrar_comprador(new_p, new_c)
            st.rerun()

    if st.checkbox("🔍 Gestionar Registros"):
        df_m = obtener_compradores_autorizados()
        if not df_m.empty:
            opciones_borrar = {row['id']: f"{row['nombre']} - ({row['comprador_habitual']})" for _, row in df_m.iterrows()}
            id_del = st.selectbox("Eliminar:", options=list(opciones_borrar.keys()), format_func=lambda x: opciones_borrar[x])
            if st.button("🗑️ Eliminar"):
                eliminar_comprador(id_del)
                st.rerun()

# --- 4. ÁREA PRINCIPAL ---
st.title("📅 Monitor de Órdenes de Compra")

c1, c2, c3 = st.columns([1,2,1])
with c1:
    if st.button("⬅️ Semana Anterior"):
        st.session_state.fecha_referencia -= timedelta(days=7)
        st.rerun()
with c3:
    if st.button("Siguiente Semana ➡️"):
        st.session_state.fecha_referencia += timedelta(days=7)
        st.rerun()

st.info(f"Visualizando Planificación de la Semana: **{st.session_state.fecha_referencia}**")

# Mostrar tabla (siempre cargando con herencia)
cal_data_display = cargar_semana(st.session_state.fecha_referencia)
df_display = pd.DataFrame.from_dict(cal_data_display, orient='index').transpose().fillna("-")
st.dataframe(df_display, use_container_width=True, hide_index=True)

st.divider()

# --- 5. MONITOREO ---
st.subheader("🤖 Monitoreo en Tiempo Real")
dia_hoy_es = dias_list[datetime.now().weekday()]
provs_hoy = [p for p in cal_data_display.get(dia_hoy_es, []) if p != "-"]

if not provs_hoy:
    st.warning(f"No hay proveedores programados para hoy ({dia_hoy_es}).")
else:
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
            if not any(p in p_ex for p in provs_hoy): return False
            return f"{p_ex}|{c_ex}" in set_aut

        df_filtrado = df_raw[df_raw.apply(validar, axis=1)].copy()

        if not df_filtrado.empty:
            st.success(f"Órdenes detectadas para {dia_hoy_es}:")
            st.table(df_filtrado[['Número de orden', 'Proveedor', 'Estatus', 'Comprador']])
        else:
            st.info(f"✅ Todo al día para {dia_hoy_es}.")
    except Exception as e:
        st.error(f"Error: {e}")
