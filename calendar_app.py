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
    cursor.execute('''CREATE TABLE IF NOT EXISTS proveedores_maestro 
                      (id INTEGER PRIMARY KEY, nombre TEXT UNIQUE, comprador_habitual TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS calendario_historico 
                      (id INTEGER PRIMARY KEY, fecha_semana TEXT, dia_semana TEXT, proveedores TEXT)''')
    # Crear un índice único para evitar errores en INSERT OR REPLACE
    cursor.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_fecha_dia 
                      ON calendario_historico (fecha_semana, dia_semana)''')
    conn.commit()
    conn.close()

# Ejecutar inmediatamente después de definirla
init_db()

def guardar_calendario(fecha, calendario_dict):
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    for dia, lista_provs in calendario_dict.items():
        provs_str = ",".join(lista_provs)
        cursor.execute('''INSERT OR REPLACE INTO calendario_historico (fecha_semana, dia_semana, proveedores) 
                          VALUES (?, ?, ?)''', (fecha, dia, provs_str))
    conn.commit()
    conn.close()

def cargar_semana(fecha):
    conn = sqlite3.connect('calendario.db')
    try:
        # Convertimos la fecha a string para asegurar compatibilidad con SQLite
        fecha_str = str(fecha) 
        df = pd.read_sql_query(
            "SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?", 
            conn, 
            params=(fecha_str,)
        )
        conn.close()
        if df.empty:
            return None
        return dict(zip(df['dia_semana'], df['proveedores'].apply(lambda x: x.split(',') if x else [])))
    except Exception as e:
        conn.close()
        return None

# --- 2. LÓGICA DE FECHAS Y NAVEGACIÓN ---
if 'fecha_referencia' not in st.session_state:
    hoy = datetime.now()
    st.session_state.fecha_referencia = (hoy - timedelta(days=hoy.weekday())).date()

# --- 3. SIDEBAR (UX PROFESIONAL) ---
with st.sidebar:
    st.header("⚙️ Menú de Configuración")
    st.info(f"Semana: {st.session_state.fecha_referencia}")
    
    # Navegación de semanas
    col_nav1, col_nav2 = st.columns(2)
    if col_nav1.button("⬅️ Anterior"):
        st.session_state.fecha_referencia -= timedelta(days=7)
        st.rerun()
    if col_nav2.button("Siguiente ➡️"):
        st.session_state.fecha_referencia += timedelta(days=7)
        st.rerun()

    st.divider()
    st.subheader("Edición Rápida")
    dia_edit = st.selectbox("Día para editar:", ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"])
    
    # Cargar datos actuales para el editor
    cal_actual = cargar_semana(st.session_state.fecha_referencia) or {d: [] for d in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]}
    provs_input = st.text_area(f"Proveedores para {dia_edit}:", value=", ".join(cal_actual.get(dia_edit, [])))
    
    if st.button("💾 Guardar en Base de Datos", use_container_width=True):
        cal_actual[dia_edit] = [p.strip().upper() for p in provs_input.split(",") if p.strip()]
        guardar_calendario(st.session_state.fecha_referencia, cal_actual)
        st.success("¡Datos persistidos!")
        st.rerun()

# --- 4. ÁREA PRINCIPAL ---
st.title("📅 Gestión de Calendario de Proveedores")

# Historial Visual (Indicators)
st.markdown("### Vista de Planificación")
cols_h = st.columns(4)
for i, offset in enumerate([-21, -14, -7, 0]):
    f = st.session_state.fecha_referencia + timedelta(days=offset)
    with cols_h[i]:
        color = "🟢" if cargar_semana(f) else "⚪"
        label = "Actual" if offset == 0 else f"Semana {f.strftime('%W')}"
        st.metric(label=f"{color} {label}", value=f.strftime("%d-%m"))

# Tabla Maestra con Data Editor
cal_data = cargar_semana(st.session_state.fecha_referencia) or {d: ["-"] for d in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]}
df_view = pd.DataFrame.from_dict(cal_data, orient='index').transpose()

edited_df = st.data_editor(df_view, use_container_width=True, num_rows="dynamic", key="plan_editor")

st.divider()

# --- 5. EJECUCIÓN RPA REFACTORIZADA ---
st.subheader("🤖 Ejecución de RPA")
#sucursal = st.selectbox("Sucursal:", ["CENDI GUATIRE", "CENDI 4 DE MAYO"])

if st.button("🚀 Iniciar Monitoreo Consolidado", type="primary"):
    dia_hoy_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"][datetime.now().weekday()]
    provs_hoy = cal_actual.get(dia_hoy_es, [])

    if not provs_hoy or provs_hoy == ["-"]:
        st.warning(f"No hay proveedores programados para hoy ({dia_hoy_es}).")
    else:
        with st.spinner("Descargando reporte y consolidando órdenes..."):
            url = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/%C3%93rdenes%20de%20compra%2016_04_2026.xlsx"
            try:
                res = requests.get(url)
                df_raw = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
                df_raw.columns = df_raw.columns.str.strip()

                # Consolidación (Eliminamos st.expander)
                mask = df_raw['Proveedor'].astype(str).str.upper().apply(lambda x: any(p in x for p in provs_hoy))
                df_filtrado = df_raw[mask].copy()

                if not df_filtrado.empty:
                    st.subheader(f"📋 Órdenes de Compra - {dia_hoy_es}")
                    
                    # Mapeo de Comprador
                    df_filtrado = df_filtrado.rename(columns={'Creado por': 'Comprador'})
                    
                    columnas_finales = ['Número de orden', 'Proveedor', 'Estatus', 'Tipo de entrega', 'Tipo de distribución', 'Comprador']
                    
                    # Visualización en Tabla Maestra (UX Requerida)
                    st.dataframe(
                        df_filtrado[columnas_finales],
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Número de orden": st.column_config.TextColumn("N° Orden"),
                            "Estatus": st.column_config.SelectboxColumn("Estado", options=["Autorizada", "Pendiente"], default="Autorizada"),
                            "Comprador": st.column_config.TextColumn("Comprador Asignado")
                        }
                    )
                else:
                    st.info("✅ No se encontraron órdenes activas para los proveedores de hoy.")
            except Exception as e:
                st.error(f"Error técnico: {e}")

# Inicialización de DB al final para asegurar que Streamlit cargue primero
init_db()
