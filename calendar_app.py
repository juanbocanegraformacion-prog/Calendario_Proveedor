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

# --- LÓGICA DE HERENCIA MEJORADA ---
def cargar_semana(fecha_consulta):
    conn = sqlite3.connect('calendario.db')
    fecha_str = str(fecha_consulta)
    
    # 1. Intentar cargar la semana exacta
    df = pd.read_sql_query("SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?", 
                           conn, params=(fecha_str,))
    
    if not df.empty and df['proveedores'].str.len().sum() > 0:
        res = dict(zip(df['dia_semana'], df['proveedores'].apply(lambda x: x.split(',') if x else [])))
        conn.close()
        return res
    
    # 2. Si está vacío, buscar la ÚLTIMA planificación registrada en cualquier fecha anterior
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(fecha_semana) FROM calendario_historico WHERE proveedores != '' AND fecha_semana < ?", (fecha_str,))
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

def obtener_compradores_autorizados():
    conn = sqlite3.connect('calendario.db')
    df = pd.read_sql_query("SELECT nombre, comprador_habitual FROM proveedores_maestro", conn)
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
    
    # Cargar datos actuales (con herencia)
    datos_actuales = cargar_semana(st.session_state.fecha_referencia)
    
    provs_input = st.text_area("Proveedores para este día (separados por coma):", 
                               value=", ".join(datos_actuales.get(dia_edit, [])))

    if st.button("💾 Guardar y Aplicar a Futuro"):
        datos_actuales[dia_edit] = [p.strip().upper() for p in provs_input.split(",") if p.strip()]
        guardar_calendario(st.session_state.fecha_referencia, datos_actuales)
        st.success("Planificación guardada.")
        st.rerun()

    st.divider()
    st.subheader("👤 Registro de Compradores")
    new_p = st.text_input("Nombre Proveedor:")
    new_c = st.text_input("Nombre Comprador:")
    if st.button("➕ Registrar"):
        if new_p and new_c:
            conn = sqlite3.connect('calendario.db')
            conn.execute("INSERT INTO proveedores_maestro (nombre, comprador_habitual) VALUES (?, ?)", 
                         (new_p.strip().upper(), new_c.strip().upper()))
            conn.commit()
            conn.close()
            st.rerun()

# --- 4. ÁREA PRINCIPAL ---
st.title("📅 Monitor de Órdenes de Compra")

col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])
with col_nav1:
    if st.button("⬅️ Semana Anterior"):
        st.session_state.fecha_referencia -= timedelta(days=7)
        st.rerun()
with col_nav3:
    if st.button("Siguiente Semana ➡️"):
        st.session_state.fecha_referencia += timedelta(days=7)
        st.rerun()

st.subheader(f"Planificación Semana: {st.session_state.fecha_referencia}")

# Carga la planificación (si la semana es nueva, hereda de la anterior)
plan_visual = cargar_semana(st.session_state.fecha_referencia)

# Mostrar la tabla
df_tabla = pd.DataFrame.from_dict(plan_visual, orient='index').transpose().fillna("-")
st.dataframe(df_tabla, use_container_width=True, hide_index=True)

st.divider()

# --- 5. MONITOREO EN TIEMPO REAL ---
st.subheader("🤖 Monitoreo de Órdenes")
dia_hoy_es = dias_semana[datetime.now().weekday()]
provs_planificados_hoy = [p.strip().upper() for p in plan_visual.get(dia_hoy_es, []) if p and p != "-"]

if not provs_planificados_hoy:
    st.info(f"No hay proveedores en la agenda para hoy ({dia_hoy_es}).")
else:
    url_excel = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/ODC_alerta.xlsx"
    try:
        res = requests.get(url_excel)
        df_raw = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
        
        # Limpieza de datos del Excel
        df_raw.columns = df_raw.columns.str.strip()
        df_raw = df_raw.rename(columns={'Creado por': 'Comprador'})
        df_raw['Proveedor'] = df_raw['Proveedor'].astype(str).str.upper().str.strip()
        df_raw['Comprador'] = df_raw['Comprador'].astype(str).str.upper().str.strip()

        # Obtener compradores autorizados
        df_maestro = obtener_compradores_autorizados()
        df_maestro['nombre'] = df_maestro['nombre'].str.upper().str.strip()
        df_maestro['comprador_habitual'] = df_maestro['comprador_habitual'].str.upper().str.strip()

        # Función de validación mejorada
        def validar_orden(row):
            proveedor_excel = row['Proveedor']
            comprador_excel = row['Comprador']
            
            # 1. ¿El proveedor del excel está en la lista de hoy?
            esta_en_agenda = any(p in proveedor_excel for p in provs_planificados_hoy)
            if not esta_en_agenda:
                return False
            
            # 2. ¿El comprador que hizo la orden es el autorizado para ese proveedor?
            # Buscamos en el maestro todas las parejas (Proveedor, Comprador) registradas
            autorizado = df_maestro[
                (df_maestro['nombre'].apply(lambda x: x in proveedor_excel)) & 
                (df_maestro['comprador_habitual'] == comprador_excel)
            ]
            
            return not autorizado.empty

        df_filtrado = df_raw[df_raw.apply(validar_orden, axis=1)].copy()

        if not df_filtrado.empty:
            st.success(f"Órdenes encontradas para hoy ({dia_hoy_es}):")
            st.dataframe(df_filtrado[['Número de orden', 'Proveedor', 'Estatus', 'Comprador']], 
                         use_container_width=True, hide_index=True)
        else:
            st.warning(f"No se encontraron órdenes que coincidan con los proveedores de hoy y sus compradores registrados.")
            
    except Exception as e:
        st.error(f"Error al conectar con los datos: {e}")
