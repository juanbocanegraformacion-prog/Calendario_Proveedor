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
    # Tabla Maestro: Permite múltiples compradores para un mismo proveedor
    cursor.execute('''CREATE TABLE IF NOT EXISTS proveedores_maestro 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       nombre TEXT, 
                       comprador_habitual TEXT)''')
    
    # Tabla de Calendario Semanal
    cursor.execute('''CREATE TABLE IF NOT EXISTS calendario_historico 
                      (id INTEGER PRIMARY KEY, fecha_semana TEXT, dia_semana TEXT, proveedores TEXT)''')
    
    # Índice para evitar duplicidad de días en una misma semana
    cursor.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_fecha_dia 
                      ON calendario_historico (fecha_semana, dia_semana)''')
    conn.commit()
    conn.close()

def forzar_reset_maestro():
    """Borra la tabla de maestros para corregir errores de estructura antigua (UNIQUE)"""
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS proveedores_maestro")
    conn.commit()
    conn.close()
    st.cache_data.clear()

# Inicialización
init_db()

def registrar_comprador(proveedor, comprador):
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    p_up, c_up = proveedor.strip().upper(), comprador.strip().upper()
    try:
        # Verificar si ya existe el par exacto
        cursor.execute("SELECT 1 FROM proveedores_maestro WHERE nombre = ? AND comprador_habitual = ?", (p_up, c_up))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO proveedores_maestro (nombre, comprador_habitual) VALUES (?, ?)", (p_up, c_up))
            conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def obtener_compradores_autorizados():
    conn = sqlite3.connect('calendario.db')
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
    df = pd.read_sql_query("SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?", 
                           conn, params=(str(fecha),))
    conn.close()
    if df.empty: return None
    return dict(zip(df['dia_semana'], df['proveedores'].apply(lambda x: x.split(',') if x else [])))

# --- 2. LÓGICA DE FECHAS ---
if 'fecha_referencia' not in st.session_state:
    hoy = datetime.now()
    st.session_state.fecha_referencia = (hoy - timedelta(days=hoy.weekday())).date()

# --- 3. SIDEBAR (CONFIGURACIÓN) ---
with st.sidebar:
    st.header("⚙️ Panel de Configuración")
    
    # BOTÓN DE REPARACIÓN (Para el error de integridad)
    with st.expander("🛠️ Herramientas de Sistema"):
        if st.button("Reparar Base de Datos", help="Usa esto si recibes 'Error de Integridad'"):
            forzar_reset_maestro()
            st.success("Tabla reseteada. Recarga la página.")
            st.rerun()

    st.divider()

    # Gestión de Calendario
    st.subheader("📅 Planificación Semanal")
    dia_edit = st.selectbox("Día:", ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"])
    cal_actual = cargar_semana(st.session_state.fecha_referencia) or {d: [] for d in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]}
    provs_input = st.text_area("Proveedores (sep. por coma):", value=", ".join(cal_actual.get(dia_edit, [])))

    # Gestión de Compradores (Debajo de proveedores)
    st.divider()
    st.subheader("👤 Registro de Compradores")
    new_p = st.text_input("Proveedor (Ej: POLAR):")
    new_c = st.text_input("Comprador (Ej: JESUS PEREZ):")
    
    if st.button("💾 Guardar Cambios"):
        # 1. Guardar calendario
        cal_actual[dia_edit] = [p.strip().upper() for p in provs_input.split(",") if p.strip()]
        guardar_calendario(st.session_state.fecha_referencia, cal_actual)
        
        # 2. Registrar comprador (si hay datos)
        if new_p and new_c:
            exito = registrar_comprador(new_p, new_c)
            if not exito:
                st.error("Error de integridad. Use 'Reparar Base de Datos' arriba.")
            else:
                st.success(f"Vinculado {new_c} a {new_p}")
        else:
            st.success("Calendario actualizado")
        st.rerun()

    if st.checkbox("Ver Compradores Registrados"):
        st.table(obtener_compradores_autorizados())

# --- 4. ÁREA PRINCIPAL ---
st.title("📅 Monitor de Órdenes de Compra")

# Navegación Semanal
c1, c2, c3 = st.columns([1,2,1])
with c1:
    if st.button("⬅️ Anterior"):
        st.session_state.fecha_referencia -= timedelta(days=7)
        st.rerun()
with c3:
    if st.button("Siguiente ➡️"):
        st.session_state.fecha_referencia += timedelta(days=7)
        st.rerun()

st.markdown(f"### Vista de Planificación: Semana del {st.session_state.fecha_referencia}")
cal_data = cargar_semana(st.session_state.fecha_referencia) or {d: ["-"] for d in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]}
st.data_editor(pd.DataFrame.from_dict(cal_data, orient='index').transpose(), use_container_width=True, hide_index=True)

st.divider()

# --- 5. EJECUCIÓN RPA ---
st.subheader("🤖 Ejecución de RPA")

if st.button("🚀 Iniciar Monitoreo de Hoy", type="primary"):
    dia_hoy_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"][datetime.now().weekday()]
    provs_hoy = cal_actual.get(dia_hoy_es, [])

    if not provs_hoy or provs_hoy == ["-"]:
        st.warning(f"No hay proveedores programados para hoy ({dia_hoy_es}).")
    else:
        with st.spinner("Procesando reporte y validando compradores..."):
            url = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/%C3%93rdenes%20de%20compra%2016_04_2026.xlsx"
            try:
                res = requests.get(url)
                df_raw = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
                df_raw.columns = df_raw.columns.str.strip()
                df_raw = df_raw.rename(columns={'Creado por': 'Comprador'})

                # Obtener autorizados
                df_aut = obtener_compradores_autorizados()
                df_aut['key'] = df_aut['nombre'] + "|" + df_aut['comprador_habitual']
                set_autorizados = set(df_aut['key'].tolist())

                def validar(row):
                    p_ex = str(row['Proveedor']).upper().strip()
                    c_ex = str(row['Comprador']).upper().strip()
                    # 1. ¿Está el proveedor en el calendario de hoy?
                    if not any(p in p_ex for p in provs_hoy): return False
                    # 2. ¿La pareja Proveedor|Comprador es válida en el maestro?
                    return f"{p_ex}|{c_ex}" in set_autorizados

                df_filtrado = df_raw[df_raw.apply(validar, axis=1)].copy()

                if not df_filtrado.empty:
                    st.subheader(f"📋 Órdenes de Compra Validadas - {dia_hoy_es}")
                    cols = ['Número de orden', 'Proveedor', 'Estatus', 'Tipo de entrega', 'Comprador']
                    st.dataframe(df_filtrado[cols], use_container_width=True, hide_index=True)
                else:
                    st.info("✅ No hay órdenes que coincidan con los proveedores de hoy y sus compradores autorizados.")
            except Exception as e:
                st.error(f"Error técnico: {e}")
