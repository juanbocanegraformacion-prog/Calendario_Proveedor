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
    # Tabla Maestro
    cursor.execute('''CREATE TABLE IF NOT EXISTS proveedores_maestro 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       nombre TEXT, 
                       comprador_habitual TEXT)''')
    # Tabla de Calendario con Historial
    cursor.execute('''CREATE TABLE IF NOT EXISTS calendario_historico 
                      (id INTEGER PRIMARY KEY, fecha_semana TEXT, dia_semana TEXT, proveedores TEXT)''')
    
    cursor.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_fecha_dia 
                      ON calendario_historico (fecha_semana, dia_semana)''')
    conn.commit()
    conn.close()

init_db()

def obtener_compradores_autorizados():
    conn = sqlite3.connect('calendario.db')
    df = pd.read_sql_query("SELECT id, nombre, comprador_habitual FROM proveedores_maestro", conn)
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

def cargar_semana(fecha_target):
    """
    Busca la planificación de la fecha solicitada. 
    Si no existe, busca en la semana anterior (Herencia).
    """
    conn = sqlite3.connect('calendario.db')
    
    # Intento 1: Cargar la semana específica
    df = pd.read_sql_query("SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?", 
                           conn, params=(str(fecha_target),))
    
    # Intento 2: Si está vacío, buscar la semana inmediata anterior
    if df.empty:
        fecha_anterior = fecha_target - timedelta(days=7)
        df = pd.read_sql_query("SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?", 
                               conn, params=(str(fecha_anterior),))
        if not df.empty:
            st.toast(f"Copiando planificación de la semana anterior ({fecha_anterior})")
    
    conn.close()
    
    if df.empty:
        return {d: [] for d in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]}
    
    return dict(zip(df['dia_semana'], df['proveedores'].apply(lambda x: x.split(',') if x else [])))

def procesar_cambios_maestro(cambios):
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    df_actual = obtener_compradores_autorizados()
    
    if "deleted_rows" in cambios:
        for idx in cambios["deleted_rows"]:
            id_db = df_actual.iloc[idx]['id']
            cursor.execute("DELETE FROM proveedores_maestro WHERE id = ?", (int(id_db),))
            
    if "edited_rows" in cambios:
        for idx_str, datos in cambios["edited_rows"].items():
            id_db = df_actual.iloc[int(idx_str)]['id']
            for campo, valor in datos.items():
                cursor.execute(f"UPDATE proveedores_maestro SET {campo} = ? WHERE id = ?", 
                             (str(valor).upper().strip(), int(id_db)))
    conn.commit()
    conn.close()

# --- 2. ESTADO DE SESIÓN Y NAVEGACIÓN ---
if 'fecha_referencia' not in st.session_state:
    hoy = datetime.now()
    st.session_state.fecha_referencia = (hoy - timedelta(days=hoy.weekday())).date()

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Configuración")
    
    # SECCIÓN A: PLANIFICACIÓN (Día a día)
    st.subheader("📅 Planificador")
    dia_edit = st.selectbox("Día a editar:", ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"])
    
    # Cargamos la semana (con lógica de herencia si es nueva)
    cal_actual = cargar_semana(st.session_state.fecha_referencia)
    
    provs_input = st.text_area("Proveedores (sep. por coma):", 
                              value=", ".join(cal_actual.get(dia_edit, [])),
                              help="Los cambios se guardarán solo para la semana seleccionada.")

    # SECCIÓN B: REGISTRO MAESTRO
    st.divider()
    st.subheader("👤 Maestro de Compradores")
    new_p = st.text_input("Nuevo Proveedor:")
    new_c = st.text_input("Nuevo Comprador:")
    
    if st.button("💾 Guardar Todo"):
        # Guardar calendario para la semana actual
        cal_actual[dia_edit] = [p.strip().upper() for p in provs_input.split(",") if p.strip()]
        guardar_calendario(st.session_state.fecha_referencia, cal_actual)
        
        # Registrar en maestro si hay datos
        if new_p and new_c:
            conn = sqlite3.connect('calendario.db')
            conn.execute("INSERT INTO proveedores_maestro (nombre, comprador_habitual) VALUES (?, ?)", 
                         (new_p.upper().strip(), new_c.upper().strip()))
            conn.commit()
            conn.close()
        st.rerun()

    # SECCIÓN C: GESTIÓN DE MAESTRO
    st.divider()
    if st.checkbox("🛠️ Editar/Eliminar Compradores"):
        df_m = obtener_compradores_autorizados()
        edit_maestro = st.data_editor(df_m, column_config={"id": None}, hide_index=True, num_rows="dynamic", key="editor_m")
        if st.button("Confirmar Cambios Maestro"):
            procesar_cambios_maestro(st.session_state.editor_m)
            st.rerun()

# --- 4. ÁREA PRINCIPAL ---
st.title("📅 Monitor de Órdenes de Compra")

c1, c2, c3 = st.columns([1,2,1])
with c1:
    if st.button("⬅️ Semana Anterior"):
        st.session_state.fecha_referencia -= timedelta(days=7)
        st.rerun()
with c3:
    if st.button("Semana Siguiente ➡️"):
        st.session_state.fecha_referencia += timedelta(days=7)
        st.rerun()

st.info(f"📍 Estás visualizando la semana del: **{st.session_state.fecha_referencia}**")

# Visualización de la planificación
df_viz = pd.DataFrame.from_dict(cal_actual, orient='index').transpose()
st.data_editor(df_viz, use_container_width=True, hide_index=True, key="view_plan")

st.divider()

# --- 5. MONITOREO AUTOMÁTICO ---
st.subheader("🤖 Validación de Órdenes (Hoy)")

# Lógica de detección de hoy
dias_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
dia_hoy_es = dias_es[datetime.now().weekday()]

# Verificamos si para la semana real de hoy hay planificación
plan_hoy_real = cargar_semana((datetime.now() - timedelta(days=datetime.now().weekday())).date())
provs_hoy = plan_hoy_real.get(dia_hoy_es, [])

if not provs_hoy or provs_hoy == ["-"]:
    st.warning(f"No hay proveedores definidos para hoy ({dia_hoy_es}). Revisa la planificación.")
else:
    @st.cache_data(ttl=300)
    def fetch_data(url):
        return pd.read_excel(io.BytesIO(requests.get(url).content), engine='openpyxl')

    url = "https://github.com/juanbocanegraformacion-prog/Calendario_Proveedor/blob/main/ODC_CENDI_GUATIRE_20260421_1110.xlsx"

   # https://github.com/juanbocanegraformacion-prog/Calendario_Proveedor/blob/main/ODC_CENDI_GUATIRE_20260421_1110.xlsx
    
    try:
        df_raw = fetch_data(url)
        df_raw.columns = df_raw.columns.str.strip()
        df_raw = df_raw.rename(columns={'Creado por': 'Comprador'})

        # Cargar maestros para validar
        df_maestro = obtener_compradores_autorizados()
        df_maestro['key'] = df_maestro['nombre'].str.upper().str.strip() + "|" + df_maestro['comprador_habitual'].str.upper().str.strip()
        claves_ok = set(df_maestro['key'].tolist())

        def validar(row):
            p = str(row['Proveedor']).upper().strip()
            c = str(row['Comprador']).upper().strip()
            # El proveedor debe estar en la lista de HOY
            if not any(target in p for target in provs_hoy): return False
            # La combinación Proveedor|Comprador debe estar en el MAESTRO
            return f"{p}|{c}" in claves_ok

        df_final = df_raw[df_raw.apply(validar, axis=1)].copy()

        if not df_final.empty:
            st.success(f"Se encontraron {len(df_final)} órdenes válidas para {dia_hoy_es}:")
            st.dataframe(df_final[['Número de orden', 'Proveedor', 'Estatus', 'Comprador']], use_container_width=True, hide_index=True)
        else:
            st.info(f"✅ Sin novedades. Los proveedores de hoy ({', '.join(provs_hoy)}) no tienen órdenes con compradores no autorizados.")

    except Exception as e:
        st.error(f"Error en sincronización: {e}")
