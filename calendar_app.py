import streamlit as st
import pandas as pd
import requests
import io
import sqlite3
import time
from datetime import datetime, timedelta

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Monitor ODC - RIOMARKET", layout="wide")

# --- ESTILOS CSS (DISEÑO 3D VERDE/BLANCO) ---
st.markdown("""
<style>
    /* Contenedor principal de la orden (Carousel) */
    .carousel-card {
        background-color: #FFFFFF;
        border: 10px solid #28a745; /* Verde Riomarket */
        border-radius: 25px;
        padding: 50px;
        text-align: center;
        box-shadow: 15px 15px 0px #145523; /* Efecto de profundidad 3D */
        margin: 30px auto;
        max-width: 900px;
    }
    .order-label { color: #28a745; font-size: 2rem; font-weight: 800; text-transform: uppercase; letter-spacing: 2px; }
    .order-number { font-size: 10rem; font-weight: 900; color: #1e7e34; line-height: 1; margin: 20px 0; }
    .order-provider { font-size: 3rem; font-weight: 700; color: #333; }
    .order-buyer { font-size: 1.5rem; color: #666; margin-top: 20px; font-style: italic; }
    
    /* Estilo para la tabla de la semana */
    .stDataFrame { border: 1px solid #e6e9ef; border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# --- 1. BASE DE DATOS Y LÓGICA DE PERSISTENCIA ---
def init_db():
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS proveedores_maestro 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, comprador_habitual TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS calendario_historico 
                      (id INTEGER PRIMARY KEY, fecha_semana TEXT, dia_semana TEXT, proveedores TEXT)''')
    cursor.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_fecha_dia ON calendario_historico (fecha_semana, dia_semana)''')
    conn.commit()
    conn.close()

def cargar_semana(fecha_consulta):
    conn = sqlite3.connect('calendario.db')
    f_str = str(fecha_consulta)
    df = pd.read_sql_query("SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?", conn, params=(f_str,))
    
    if not df.empty:
        res = dict(zip(df['dia_semana'], df['proveedores'].apply(lambda x: x.split(',') if x else [])))
        conn.close()
        return res
    
    # Lógica de herencia: buscar la semana más reciente anterior
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(fecha_semana) FROM calendario_historico WHERE fecha_semana < ?", (f_str,))
    ultima_f = cursor.fetchone()[0]
    
    if ultima_f:
        df_h = pd.read_sql_query("SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?", conn, params=(ultima_f,))
        conn.close()
        return dict(zip(df_h['dia_semana'], df_h['proveedores'].apply(lambda x: x.split(',') if x else [])))
    
    conn.close()
    return {d: [] for d in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]}

def guardar_datos_semana(fecha, dia, lista_provs):
    conn = sqlite3.connect('calendario.db')
    provs_str = ",".join([p.strip().upper() for p in lista_provs if p.strip()])
    conn.execute("INSERT OR REPLACE INTO calendario_historico (fecha_semana, dia_semana, proveedores) VALUES (?, ?, ?)", 
                 (str(fecha), dia, provs_str))
    conn.commit()
    conn.close()

init_db()

# --- 2. GESTIÓN DE ESTADO (ROTACIÓN) ---
if 'fecha_referencia' not in st.session_state:
    hoy = datetime.now()
    st.session_state.fecha_referencia = (hoy - timedelta(days=hoy.weekday())).date()

if 'carousel_index' not in st.session_state:
    st.session_state.carousel_index = 0

# --- 3. SIDEBAR (INTERFAZ REFACTORIZADA) ---
with st.sidebar:
    st.header("⚙️ Configuración de Sistema")
    
    # Sección 1: Planificación
    with st.expander("📅 Planificación Semanal", expanded=True):
        dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        dia_edit = st.selectbox("Día a configurar:", dias)
        cal_actual = cargar_semana(st.session_state.fecha_referencia)
        
        provs_input = st.text_area("Proveedores (sep. por coma):", 
                                   value=", ".join(cal_actual.get(dia_edit, [])))
        
        if st.button("💾 Guardar Planificación"):
            lista_nueva = [p.strip().upper() for p in provs_input.split(",") if p.strip()]
            guardar_datos_semana(st.session_state.fecha_referencia, dia_edit, lista_nueva)
            st.success(f"Agenda de {dia_edit} actualizada.")
            st.rerun()

    # Sección 2: Maestro de Compradores
    with st.expander("👤 Maestro de Compradores"):
        with st.form("nuevo_comprador"):
            np = st.text_input("Nombre Proveedor:")
            nc = st.text_input("Comprador Asignado:")
            if st.form_submit_button("➕ Registrar en Maestro"):
                if np and nc:
                    conn = sqlite3.connect('calendario.db')
                    conn.execute("INSERT INTO proveedores_maestro (nombre, comprador_habitual) VALUES (?, ?)", 
                                 (np.upper(), nc.upper()))
                    conn.commit()
                    conn.close()
                    st.rerun()
        
        # Gestión de registros existentes
        conn = sqlite3.connect('calendario.db')
        df_m = pd.read_sql_query("SELECT id, nombre, comprador_habitual FROM proveedores_maestro", conn)
        conn.close()
        
        if not df_m.empty:
            st.write("---")
            st.caption("Registros actuales (Edite o elimine):")
            st.data_editor(df_m, hide_index=True, key="editor_maestro", use_container_width=True)
            
            id_del = st.selectbox("Eliminar ID:", options=df_m['id'].tolist())
            if st.button("🗑️ Eliminar Registro"):
                conn = sqlite3.connect('calendario.db')
                conn.execute("DELETE FROM proveedores_maestro WHERE id = ?", (id_del,))
                conn.commit(); conn.close()
                st.rerun()

    # Sección 3: Zona de Peligro
    with st.expander("⚠️ Zona de Peligro"):
        if st.button("🔥 REINICIAR TODA LA DATA"):
            conn = sqlite3.connect('calendario.db')
            conn.execute("DROP TABLE IF EXISTS proveedores_maestro")
            conn.execute("DROP TABLE IF EXISTS calendario_historico")
            conn.commit(); conn.close()
            init_db()
            st.rerun()

# --- 4. CUERPO PRINCIPAL (VISUALIZACIÓN) ---
st.title("🚀 Monitor de Órdenes de Compra")

# Selector de semanas
c1, c2, c3 = st.columns([1,3,1])
with c1:
    if st.button("⬅️ Semana Anterior"): st.session_state.fecha_referencia -= timedelta(days=7); st.rerun()
with c3:
    if st.button("Siguiente Semana ➡️"): st.session_state.fecha_referencia += timedelta(days=7); st.rerun()

st.subheader(f"📅 Planificación: Semana del {st.session_state.fecha_referencia}")

# Mostrar tabla resumen
cal_data = cargar_semana(st.session_state.fecha_referencia)
df_viz = pd.DataFrame.from_dict(cal_data, orient='index').transpose().fillna("-")
st.table(df_viz) # Uso table para que se vea fija y clara

st.divider()

# --- 5. SISTEMA DE CAROUSEL (MONITOREO) ---
dia_hoy = dias[datetime.now().weekday()]
provs_hoy = cal_data.get(dia_hoy, [])

st.subheader(f"🤖 Turnos en Pantalla - {dia_hoy}")

if not provs_hoy:
    st.info(f"No hay proveedores programados para hoy {dia_hoy}. Configure la agenda en el panel izquierdo.")
else:
    url = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/ODC_alerta.xlsx"
    try:
        res = requests.get(url)
        df_raw = pd.read_excel(io.BytesIO(res.content))
        df_raw.columns = df_raw.columns.str.strip()
        df_raw = df_raw.rename(columns={'Creado por': 'Comprador'})
        
        # Obtener autorizados del maestro
        conn = sqlite3.connect('calendario.db')
        df_aut = pd.read_sql_query("SELECT nombre, comprador_habitual FROM proveedores_maestro", conn)
        conn.close()
        
        df_aut['key'] = df_aut['nombre'].str.upper() + "|" + df_aut['comprador_habitual'].str.upper()
        set_aut = set(df_aut['key'].tolist())

        def validar_orden(row):
            p, c = str(row['Proveedor']).upper().strip(), str(row['Comprador']).upper().strip()
            # Validar que el proveedor toque hoy y que el par P|C esté en el maestro
            pertence_a_hoy = any(px in p for px in provs_hoy)
            return pertence_a_hoy and f"{p}|{c}" in set_aut

        df_filtrado = df_raw[df_raw.apply(validar_orden, axis=1)].copy()

        if not df_filtrado.empty:
            ordenes = df_filtrado.sort_values(by='Número de orden', ascending=True).to_dict('records')
            
            # Lógica de rotación circular
            if st.session_state.carousel_index >= len(ordenes):
                st.session_state.carousel_index = 0
            
            orden_actual = ordenes[st.session_state.carousel_index]

            # RENDERIZADO DEL CAROUSEL (ESTILO 3D)
            st.markdown(f"""
                <div class="carousel-card">
                    <div class="order-label">Turno Actual</div>
                    <div class="order-number">{str(orden_actual['Número de orden'])[-4:]}</div>
                    <div class="order-provider">{orden_actual['Proveedor']}</div>
                    <div class="order-buyer">👤 Responsable: {orden_actual['Comprador']}</div>
                </div>
            """, unsafe_allow_html=True)

            # Pie de página del carousel
            st.caption(f"Mostrando orden {st.session_state.carousel_index + 1} de {len(ordenes)} validada(s). Próxima actualización en 6 segundos...")

            # Auto-rotación
            st.session_state.carousel_index += 1
            time.sleep(6)
            st.rerun()

        else:
            st.warning("Buscando órdenes validadas en el servidor... Si el monitor no avanza, verifique que los proveedores de hoy estén registrados en el Maestro de Compradores.")
            time.sleep(10)
            st.rerun()

    except Exception as e:
        st.error(f"Error de conexión con la base de datos externa: {e}")
