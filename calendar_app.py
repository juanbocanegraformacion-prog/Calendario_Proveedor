import streamlit as st
import pandas as pd
import requests
import io
import sqlite3
from datetime import datetime, timedelta

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Monitor ODC - RIOMARKET", layout="wide")

# --- 1. PERSISTENCIA Y BASE DE DATOS (SQLite) ---
def init_db():
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    # Cambiamos la tabla para que NO tenga UNIQUE en nombre, permitiendo varios compradores por proveedor
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

# Inicialización inmediata
init_db()

def registrar_comprador(proveedor, comprador):
    """Permite registrar múltiples compradores para un mismo proveedor"""
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    p_up, c_up = proveedor.strip().upper(), comprador.strip().upper()
    
    # Verificamos si ya existe esa combinación exacta para no duplicar
    cursor.execute("SELECT * FROM proveedores_maestro WHERE nombre = ? AND comprador_habitual = ?", (p_up, c_up))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO proveedores_maestro (nombre, comprador_habitual) VALUES (?, ?)", (p_up, c_up))
        conn.commit()
    conn.close()

def obtener_compradores_autorizados():
    conn = sqlite3.connect('calendario.db')
    # Obtenemos todos los pares válidos
    df = pd.read_sql_query("SELECT nombre, comprador_habitual FROM proveedores_maestro", conn)
    conn.close()
    return df

def guardar_calendario(fecha, calendario_dict):
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    for dia, lista_provs in calendario_dict.items():
        provs_str = ",".join(lista_provs)
        cursor.execute('''INSERT OR REPLACE INTO calendario_historico (fecha_semana, dia_semana, proveedores) 
                          VALUES (?, ?, ?)''', (str(fecha), dia, provs_str))
    conn.commit()
    conn.close()

def cargar_semana(fecha):
    conn = sqlite3.connect('calendario.db')
    try:
        df = pd.read_sql_query("SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?", 
                               conn, params=(str(fecha),))
        conn.close()
        if df.empty: return None
        return dict(zip(df['dia_semana'], df['proveedores'].apply(lambda x: x.split(',') if x else [])))
    except:
        return None

# --- 2. LÓGICA DE FECHAS ---
if 'fecha_referencia' not in st.session_state:
    hoy = datetime.now()
    st.session_state.fecha_referencia = (hoy - timedelta(days=hoy.weekday())).date()

# --- 3. SIDEBAR (CONFIGURACIÓN Y REGISTRO) ---
with st.sidebar:
    st.header("⚙️ Configuración del Monitor")
    
    # Sección 1: Gestión de Calendario
    with st.expander("📅 Editar Planificación Semanal", expanded=True):
        dia_edit = st.selectbox("Día:", ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"])
        cal_actual = cargar_semana(st.session_state.fecha_referencia) or {d: [] for d in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]}
        provs_input = st.text_area("Proveedores:", value=", ".join(cal_actual.get(dia_edit, [])))
        
        if st.button("💾 Guardar Planificación"):
            cal_actual[dia_edit] = [p.strip().upper() for p in provs_input.split(",") if p.strip()]
            guardar_calendario(st.session_state.fecha_referencia, cal_actual)
            st.success("Calendario guardado")
            st.rerun()

    st.divider()

    # Sección 2: Registro de Compradores (NUEVA FUNCIÓN)
    with st.expander("👤 Registro de Compradores Autorizados"):
        st.caption("Un proveedor puede tener varios compradores registrados.")
        new_prov = st.text_input("Proveedor (Ej: POLAR)")
        new_comp = st.text_input("Comprador (Ej: JESUS PEREZ)")
        
        if st.button("➕ Vincular Comprador"):
            if new_prov and new_comp:
                registrar_comprador(new_prov, new_comp)
                st.success(f"Vinculado {new_comp} a {new_prov}")
            else:
                st.error("Complete ambos campos")

    # Mostrar lista actual de autorizados
    if st.checkbox("Ver Compradores Registrados"):
        st.table(obtener_compradores_autorizados())

# --- 4. ÁREA PRINCIPAL ---
st.title("📅 Gestión de Calendario de Proveedores")

# Navegación de semanas (Simple)
c1, c2, c3 = st.columns([1,2,1])
if c1.button("⬅️ Semana Anterior"):
    st.session_state.fecha_referencia -= timedelta(days=7)
    st.rerun()
if c3.button("Semana Siguiente ➡️"):
    st.session_state.fecha_referencia += timedelta(days=7)
    st.rerun()

# Tabla de Planificación
st.markdown(f"### Planificación Semana: {st.session_state.fecha_referencia}")
cal_data = cargar_semana(st.session_state.fecha_referencia) or {d: ["-"] for d in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]}
st.data_editor(pd.DataFrame.from_dict(cal_data, orient='index').transpose(), use_container_width=True)

st.divider()

# --- 5. EJECUCIÓN RPA CON FILTRO MULTI-COMPRADOR ---
st.subheader("🤖 Ejecución de RPA")

if st.button("🚀 Iniciar Monitoreo Consolidado", type="primary"):
    dia_idx = datetime.now().weekday()
    dias_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    dia_hoy_es = dias_es[dia_idx]
    provs_hoy = cal_actual.get(dia_hoy_es, [])

    if not provs_hoy:
        st.warning(f"No hay proveedores para hoy ({dia_hoy_es}).")
    else:
        with st.spinner("Consultando órdenes y validando compradores..."):
            url = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/%C3%93rdenes%20de%20compra%2016_04_2026.xlsx"
            try:
                res = requests.get(url)
                df_raw = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
                df_raw.columns = df_raw.columns.str.strip()
                df_raw = df_raw.rename(columns={'Creado por': 'Comprador'})

                # 1. Obtener los pares Autorizados (Proveedor-Comprador) de la DB
                df_autorizados = obtener_compradores_autorizados()
                df_autorizados['key'] = df_autorizados['nombre'] + "|" + df_autorizados['comprador_habitual']
                set_autorizados = set(df_autorizados['key'].tolist())

                # 2. Filtrar el reporte de Excel
                def validar_fila(row):
                    p_excel = str(row['Proveedor']).upper().strip()
                    c_excel = str(row['Comprador']).upper().strip()
                    
                    # ¿El proveedor está en mi plan de hoy?
                    if not any(p in p_excel for p in provs_hoy):
                        return False
                    
                    # ¿La combinación Proveedor|Comprador está autorizada en mi DB?
                    # Usamos 'in' sobre el set para máxima velocidad
                    key_excel = f"{p_excel}|{c_excel}"
                    return key_excel in set_autorizados

                df_filtrado = df_raw[df_raw.apply(validar_fila, axis=1)].copy()

                if not df_filtrado.empty:
                    st.subheader(f"📋 Órdenes Validadas - {dia_hoy_es}")
                    columnas_finales = ['Número de orden', 'Proveedor', 'Estatus', 'Tipo de entrega', 'Comprador']
                    st.dataframe(df_filtrado[columnas_finales], use_container_width=True, hide_index=True)
                else:
                    st.info("✅ No hay órdenes que coincidan con los proveedores de hoy y sus compradores autorizados.")
            
            except Exception as e:
                st.error(f"Error en el proceso: {e}")
