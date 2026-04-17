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

def obtener_compradores_autorizados():
    conn = sqlite3.connect('calendario.db')
    df = pd.read_sql_query("SELECT id, nombre, comprador_habitual FROM proveedores_maestro", conn)
    conn.close()
    return df

def registrar_comprador(proveedor, comprador):
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    p_up, c_up = proveedor.strip().upper(), comprador.strip().upper()
    cursor.execute("INSERT INTO proveedores_maestro (nombre, comprador_habitual) VALUES (?, ?)", (p_up, c_up))
    conn.commit()
    conn.close()

def procesar_cambios_db(cambios):
    """Procesa las ediciones y eliminaciones del data_editor"""
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    
    # 1. Eliminar registros
    if "deleted_rows" in cambios and cambios["deleted_rows"]:
        # El editor nos da el índice de la fila, necesitamos el ID real
        df_actual = obtener_compradores_autorizados()
        for idx in cambios["deleted_rows"]:
            id_db = df_actual.iloc[idx]['id']
            cursor.execute("DELETE FROM proveedores_maestro WHERE id = ?", (int(id_db),))
    
    # 2. Modificar registros existentes
    if "edited_rows" in cambios and cambios["edited_rows"]:
        df_actual = obtener_compradores_autorizados()
        for idx_str, datos in cambios["edited_rows"].items():
            idx = int(idx_str)
            id_db = df_actual.iloc[idx]['id']
            # Actualizamos solo los campos que cambiaron
            for campo, valor in datos.items():
                cursor.execute(f"UPDATE proveedores_maestro SET {campo} = ? WHERE id = ?", 
                             (str(valor).upper().strip(), int(id_db)))
    
    conn.commit()
    conn.close()

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

# --- 2. LÓGICA DE NAVEGACIÓN ---
if 'fecha_referencia' not in st.session_state:
    hoy = datetime.now()
    st.session_state.fecha_referencia = (hoy - timedelta(days=hoy.weekday())).date()

# --- 3. SIDEBAR (GESTIÓN) ---
with st.sidebar:
    st.header("⚙️ Configuración")
    
    # A. PLANIFICACIÓN
    st.subheader("📅 Planificación Semanal")
    dia_edit = st.selectbox("Día:", ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"])
    cal_actual = cargar_semana(st.session_state.fecha_referencia) or {d: [] for d in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]}
    provs_input = st.text_area("Proveedores:", value=", ".join(cal_actual.get(dia_edit, [])))

    # B. REGISTRO NUEVO
    st.divider()
    st.subheader("👤 Nuevo Comprador")
    new_p = st.text_input("Proveedor:")
    new_c = st.text_input("Comprador:")
    
    if st.button("💾 Guardar Planificación y Nuevo"):
        cal_actual[dia_edit] = [p.strip().upper() for p in provs_input.split(",") if p.strip()]
        guardar_calendario(st.session_state.fecha_referencia, cal_actual)
        if new_p and new_c:
            registrar_comprador(new_p, new_c)
        st.rerun()

    # C. GESTIÓN DINÁMICA (MODIFICAR/ELIMINAR)
    st.divider()
    st.subheader("📋 Gestión de Maestros")
    df_compradores = obtener_compradores_autorizados()
    
    if not df_compradores.empty:
        st.info("💡 Edite celdas para **Modificar** o use el icono de papelera para **Eliminar**.")
        # El data_editor gestiona automáticamente las acciones
        cambios = st.data_editor(
            df_compradores,
            column_config={
                "id": None, # Ocultamos el ID interno
                "nombre": st.column_config.TextColumn("Proveedor"),
                "comprador_habitual": st.column_config.TextColumn("Comprador")
            },
            num_rows="dynamic", # Permite eliminar filas
            hide_index=True,
            use_container_width=True,
            key="gestor_maestro"
        )
        
        # Si hay cambios detectados, procesamos la DB
        if st.button("✅ Confirmar Cambios en Maestro"):
            procesar_cambios_db(st.session_state.gestor_maestro)
            st.success("Base de Datos actualizada")
            st.rerun()
    else:
        st.caption("No hay compradores registrados.")

# --- 4. ÁREA PRINCIPAL ---
st.title("📅 Monitor de Órdenes de Compra")

col1, col2, col3 = st.columns([1,2,1])
with col1:
    if st.button("⬅️ Anterior"):
        st.session_state.fecha_referencia -= timedelta(days=7)
        st.rerun()
with col3:
    if st.button("Siguiente ➡️"):
        st.session_state.fecha_referencia += timedelta(days=7)
        st.rerun()

st.markdown(f"### Planificación Semana: {st.session_state.fecha_referencia}")
cal_data = cargar_semana(st.session_state.fecha_referencia) or {d: ["-"] for d in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]}
st.data_editor(pd.DataFrame.from_dict(cal_data, orient='index').transpose(), use_container_width=True, hide_index=True)

st.divider()

# --- 5. MONITOREO AUTOMÁTICO ---
st.subheader("🤖 Monitoreo en Tiempo Real")

dia_hoy_idx = datetime.now().weekday()
dias_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
dia_hoy_es = dias_es[dia_hoy_idx]
provs_hoy = cal_actual.get(dia_hoy_es, [])

if not provs_hoy or provs_hoy == ["-"]:
    st.info(f"Sin proveedores para hoy ({dia_hoy_es}).")
else:
    @st.cache_data(ttl=300)
    def buscar_excel(url):
        r = requests.get(url)
        return pd.read_excel(io.BytesIO(r.content), engine='openpyxl')

    url = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/%C3%93rdenes%20de%20compra%2016_04_2026.xlsx"
    
    try:
        df_raw = buscar_excel(url)
        df_raw.columns = df_raw.columns.str.strip()
        df_raw = df_raw.rename(columns={'Creado por': 'Comprador'})

        df_m = obtener_compradores_autorizados()
        df_m['key'] = df_m['nombre'].str.upper().str.strip() + "|" + df_m['comprador_habitual'].str.upper().str.strip()
        claves_validas = set(df_m['key'].tolist())

        def validar_fila(row):
            p = str(row['Proveedor']).upper().strip()
            c = str(row['Comprador']).upper().strip()
            if not any(target in p for target in provs_hoy): return False
            return f"{p}|{c}" in claves_validas

        df_final = df_raw[df_raw.apply(validar_fila, axis=1)].copy()

        if not df_final.empty:
            st.success(f"Órdenes detectadas para hoy:")
            st.dataframe(df_final[['Número de orden', 'Proveedor', 'Estatus', 'Comprador']], use_container_width=True, hide_index=True)
        else:
            st.info("✅ Todo al día. No hay órdenes pendientes para estos criterios.")
    except Exception as e:
        st.error(f"Error de conexión: {e}")
