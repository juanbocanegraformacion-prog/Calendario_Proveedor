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
    with sqlite3.connect('calendario.db') as conn:
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

def forzar_reset_maestro():
    with sqlite3.connect('calendario.db') as conn:
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS proveedores_maestro")
        conn.commit()
    st.cache_data.clear()

init_db()

def registrar_comprador(proveedor, comprador):
    p_up, c_up = proveedor.strip().upper(), comprador.strip().upper()
    try:
        with sqlite3.connect('calendario.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM proveedores_maestro WHERE nombre = ? AND comprador_habitual = ?", (p_up, c_up))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO proveedores_maestro (nombre, comprador_habitual) VALUES (?, ?)", (p_up, c_up))
                conn.commit()
        return True
    except sqlite3.Error:
        return False

def obtener_compradores_autorizados():
    with sqlite3.connect('calendario.db') as conn:
        df = pd.read_sql_query("SELECT id, nombre, comprador_habitual FROM proveedores_maestro", conn)
    return df

def guardar_calendario(fecha, calendario_dict):
    with sqlite3.connect('calendario.db') as conn:
        cursor = conn.cursor()
        for dia, lista_provs in calendario_dict.items():
            provs_str = ",".join(lista_provs)
            cursor.execute('''INSERT OR REPLACE INTO calendario_historico (fecha_semana, dia_semana, proveedores) 
                              VALUES (?, ?, ?)''', (str(fecha), dia, provs_str))
        conn.commit()

def cargar_semana(fecha):
    with sqlite3.connect('calendario.db') as conn:
        df = pd.read_sql_query("SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?", 
                               conn, params=(str(fecha),))
    if df.empty: return None
    return dict(zip(df['dia_semana'], df['proveedores'].apply(lambda x: x.split(',') if x else [])))

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
            st.success("Tabla reseteada.")
            st.rerun()

    st.divider()
    st.subheader("📅 Planificación Semanal")
    dias_lista = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    dia_edit = st.selectbox("Seleccionar día para editar:", dias_lista)
    
    cal_actual = cargar_semana(st.session_state.fecha_referencia) or {d: [] for d in dias_lista}
    provs_input = st.text_area("Proveedores para el día (sep. por coma):", 
                               value=", ".join(cal_actual.get(dia_edit, [])),
                               help="Escribe los nombres de los proveedores separados por comas.")

    st.divider()
    st.subheader("👤 Registro de Compradores")
    new_p = st.text_input("Nombre del Proveedor:", placeholder="Ej: POLAR")
    new_c = st.text_input("Nombre del Comprador:", placeholder="Ej: JESUS PEREZ")
    
    if st.button("💾 Guardar Cambios Generales", use_container_width=True):
        # 1. Guardar calendario
        cal_actual[dia_edit] = [p.strip().upper() for p in provs_input.split(",") if p.strip()]
        guardar_calendario(st.session_state.fecha_referencia, cal_actual)
        
        # 2. Registrar comprador (si hay datos)
        if new_p and new_c:
            exito = registrar_comprador(new_p, new_c)
            if exito:
                st.success(f"Vinculado {new_c} a {new_p}")
            else:
                st.error("Error al registrar el comprador.")
        
        st.toast("Datos actualizados correctamente")
        st.rerun()

    if st.checkbox("Ver Compradores Registrados"):
        df_auth = obtener_compradores_autorizados()
        st.dataframe(df_auth, hide_index=True)

# --- 4. ÁREA PRINCIPAL ---
st.title("📅 Monitor de Órdenes de Compra")

c1, c2, c3 = st.columns([1, 2, 1])
with c1:
    if st.button("⬅️ Semana Anterior"):
        st.session_state.fecha_referencia -= timedelta(days=7)
        st.rerun()
with c3:
    if st.button("Semana Siguiente ➡️"):
        st.session_state.fecha_referencia += timedelta(days=7)
        st.rerun()

st.info(f"### Mostrando Planificación: {st.session_state.fecha_referencia}")

# Mostrar tabla de la semana
cal_data = cargar_semana(st.session_state.fecha_referencia) or {d: ["-"] for d in dias_lista}
# Ajustar longitudes para el DataFrame
max_len = max(len(v) for v in cal_data.values())
df_display = pd.DataFrame({k: v + [""] * (max_len - len(v)) for k, v in cal_data.items()})
st.table(df_display)

st.divider()

# --- 5. LÓGICA DE MONITOREO AUTOMÁTICO ---
st.subheader("🤖 Monitoreo en Tiempo Real")

dia_hoy_idx = datetime.now().weekday()
dia_hoy_es = dias_lista[dia_hoy_idx]

# Obtenemos los proveedores para el día actual desde cal_actual
provs_hoy = cal_actual.get(dia_hoy_es, [])

if not provs_hoy or provs_hoy == ["-"]:
    st.info(f"No hay proveedores programados para hoy ({dia_hoy_es}).")
else:
    @st.cache_data(ttl=300)
    def obtener_datos_github(url):
        res = requests.get(url)
        res.raise_for_status() # Lanza error si la descarga falla
        return pd.read_excel(io.BytesIO(res.content), engine='openpyxl')

    # URL del Excel (Asegúrate de que la fecha en el nombre del archivo sea correcta o dinámica)
    url_excel = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/odc_alerta.xlsx"
    
    try:
        df_raw = obtener_datos_github(url_excel)
        df_raw.columns = df_raw.columns.str.strip()
        
        # Mapeo de columnas (Asegúrate de que existan en tu Excel)
        if 'Creado por' in df_raw.columns:
            df_raw = df_raw.rename(columns={'Creado por': 'Comprador'})

        df_aut = obtener_compradores_autorizados()
        df_aut['key'] = df_aut['nombre'].str.upper().str.strip() + "|" + df_aut['comprador_habitual'].str.upper().str.strip()
        set_autorizados = set(df_aut['key'].tolist())

        def validar(row):
            p_ex = str(row.get('Proveedor', '')).upper().strip()
            c_ex = str(row.get('Comprador', '')).upper().strip()
            # Valida si el proveedor está en la lista de hoy Y el comprador está autorizado
            match_prov = any(p in p_ex for p in provs_hoy)
            match_auth = f"{p_ex}|{c_ex}" in set_autorizados
            return match_prov and match_auth

        df_filtrado = df_raw[df_raw.apply(validar, axis=1)].copy()

        if not df_filtrado.empty:
            st.success(f"Órdenes validadas encontradas para hoy ({dia_hoy_es}):")
            cols_mostrar = [c for c in ['Número de orden', 'Proveedor', 'Estatus', 'Comprador'] if c in df_filtrado.columns]
            st.dataframe(df_filtrado[cols_mostrar], use_container_width=True, hide_index=True)
        else:
            st.warning(f"No se encontraron órdenes para {dia_hoy_es} que coincidan con la planificación y compradores autorizados.")
            
    except Exception as e:
        st.error(f"Error al sincronizar datos: {e}")
