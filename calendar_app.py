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
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_fecha_semana 
                      ON calendario_historico (fecha_semana)''')
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
    except sqlite3.IntegrityError:
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

def guardar_calendario(fecha, calendario_dict):
    """Guarda la semana completa (todos los días) en la base de datos."""
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    for dia, lista_provs in calendario_dict.items():
        provs_str = ",".join(lista_provs) if lista_provs else ""
        cursor.execute('''INSERT OR REPLACE INTO calendario_historico (fecha_semana, dia_semana, proveedores) 
                          VALUES (?, ?, ?)''', (str(fecha), dia, provs_str))
    conn.commit()
    conn.close()

def cargar_semana(fecha):
    """
    Carga la planificación de una semana.
    - Si existe en BD, la devuelve.
    - Si no existe, busca la semana anterior más reciente (con datos) y la hereda.
    - Si no hay ninguna semana anterior, devuelve una semana vacía.
    """
    dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    conn = sqlite3.connect('calendario.db')
    try:
        # 1. Intentar cargar la semana exacta
        df = pd.read_sql_query(
            "SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?",
            conn, params=(str(fecha),)
        )
        if not df.empty:
            # Semana encontrada
            return _df_to_dict(df, dias_semana), False  # False = no heredado

        # 2. Buscar la semana anterior más reciente (con cualquier registro)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT fecha_semana FROM calendario_historico WHERE fecha_semana < ? ORDER BY fecha_semana DESC LIMIT 1",
            (str(fecha),)
        )
        row = cursor.fetchone()
        if row:
            fecha_anterior = row[0]
            df_prev = pd.read_sql_query(
                "SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?",
                conn, params=(fecha_anterior,)
            )
            if not df_prev.empty:
                # Devolvemos los datos de la semana anterior + flag de herencia
                return _df_to_dict(df_prev, dias_semana), True

        # 3. Sin historial: semana vacía
        return {dia: [] for dia in dias_semana}, False
    except Exception as e:
        st.error(f"Error al cargar semana {fecha}: {e}")
        return {dia: [] for dia in dias_semana}, False
    finally:
        conn.close()

def _df_to_dict(df: pd.DataFrame, dias_semana: list) -> dict:
    """Convierte un DataFrame (dia_semana, proveedores) a dict día -> lista."""
    resultado = {dia: [] for dia in dias_semana}
    for _, row in df.iterrows():
        dia = row['dia_semana']
        proveedores_str = row['proveedores']
        if proveedores_str and pd.notna(proveedores_str):
            lista = [p.strip().upper() for p in proveedores_str.split(',') if p.strip()]
            resultado[dia] = lista
        else:
            resultado[dia] = []
    return resultado

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
    dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    dia_edit = st.selectbox("Día:", dias_semana)
    
    # Cargar datos de la semana actual (con herencia)
    cal_actual, es_heredado = cargar_semana(st.session_state.fecha_referencia)
    if es_heredado:
        st.info("ℹ️ Esta semana no tiene configuración propia. Se están mostrando los datos de la semana anterior. Puedes modificarlos y guardar para crear un nuevo registro.")
    
    provs_input = st.text_area(
        "Proveedores (sep. por coma):",
        value=", ".join(cal_actual.get(dia_edit, []))
    )

    st.divider()
    st.subheader("👤 Registro de Compradores")
    new_p = st.text_input("Nuevo Proveedor:")
    new_c = st.text_input("Comprador Asignado:")
    
    if st.button("💾 Guardar Cambios"):
        # Actualizar el día editado
        cal_actual[dia_edit] = [p.strip().upper() for p in provs_input.split(",") if p.strip()]
        # Guardar la semana completa en la BD (esto crea un registro propio para esta fecha)
        guardar_calendario(st.session_state.fecha_referencia, cal_actual)
        
        if new_p and new_c:
            registrar_comprador(new_p, new_c)
        
        st.success("Datos guardados. Esta semana ahora tiene su propio registro y será heredada por semanas futuras.")
        st.rerun()

    st.divider()
    if st.checkbox("🔍 Gestionar Registros de Compradores"):
        df_m = obtener_compradores_autorizados()
        if not df_m.empty:
            st.caption("Edite directamente en la tabla o elimine un proveedor específico abajo.")
            edited_m = st.data_editor(df_m, 
                                     column_config={"id": None}, 
                                     hide_index=True, 
                                     use_container_width=True,
                                     key="editor_compradores")
            
            if st.button("🔄 Aplicar Cambios de la Tabla"):
                conn = sqlite3.connect('calendario.db')
                for index, row in edited_m.iterrows():
                    conn.execute("UPDATE proveedores_maestro SET nombre = ?, comprador_habitual = ? WHERE id = ?", 
                                 (row['nombre'].upper(), row['comprador_habitual'].upper(), row['id']))
                conn.commit()
                conn.close()
                st.success("Registros actualizados")
                st.rerun()

            st.divider()
            opciones_borrar = {row['id']: f"{row['nombre']} - ({row['comprador_habitual']})" for _, row in df_m.iterrows()}
            id_para_borrar = st.selectbox(
                "Seleccione el PROVEEDOR a eliminar:", 
                options=list(opciones_borrar.keys()),
                format_func=lambda x: opciones_borrar[x]
            )
            
            if st.button("🗑️ Eliminar Proveedor Seleccionado", type="primary"):
                eliminar_comprador(id_para_borrar)
                st.toast("Registro eliminado con éxito")
                st.rerun()
        else:
            st.info("No hay proveedores registrados.")

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

st.markdown(f"### Planificación Semana: {st.session_state.fecha_referencia}")

# Obtener datos para mostrar en la tabla principal (ya se heredan automáticamente)
cal_data, _ = cargar_semana(st.session_state.fecha_referencia)

# Convertir a DataFrame para visualización (mostrar los proveedores como lista)
df_visual = pd.DataFrame.from_dict(cal_data, orient='index').transpose().fillna("-")
st.data_editor(df_visual, use_container_width=True, hide_index=True)

st.divider()

# --- 5. LÓGICA DE MONITOREO AUTOMÁTICO ---
st.subheader("🤖 Monitoreo en Tiempo Real")

dia_hoy_idx = datetime.now().weekday()
dia_hoy_es = dias_semana[dia_hoy_idx]

provs_hoy = cal_data.get(dia_hoy_es, [])

if not provs_hoy:
    st.info(f"No hay proveedores programados para hoy ({dia_hoy_es}).")
else:
    @st.cache_data(ttl=300)
    def obtener_datos_github(url):
        try:
            res = requests.get(url)
            return pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
        except:
            return pd.DataFrame()

    url_excel = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/ODC_alerta.xlsx"
    
    try:
        df_raw = obtener_datos_github(url_excel)
        if not df_raw.empty:
            df_raw.columns = df_raw.columns.str.strip()
            df_raw = df_raw.rename(columns={'Creado por': 'Comprador'})

            df_aut = obtener_compradores_autorizados()
            df_aut['key'] = df_aut['nombre'].str.upper().str.strip() + "|" + df_aut['comprador_habitual'].str.upper().str.strip()
            set_autorizados = set(df_aut['key'].tolist())

            def validar(row):
                p_ex = str(row['Proveedor']).upper().strip()
                c_ex = str(row['Comprador']).upper().strip()
                if not any(p in p_ex for p in provs_hoy if p):
                    return False
                return f"{p_ex}|{c_ex}" in set_autorizados

            df_filtrado = df_raw[df_raw.apply(validar, axis=1)].copy()

            if not df_filtrado.empty:
                st.success(f"Órdenes validadas para hoy ({dia_hoy_es}):")
                st.dataframe(df_filtrado[['Número de orden', 'Proveedor', 'Estatus', 'Comprador']], use_container_width=True, hide_index=True)
            else:
                st.info(f"✅ Sin órdenes pendientes para {dia_hoy_es} con los compradores autorizados.")
    except Exception as e:
        st.error(f"Error al sincronizar datos: {e}")
