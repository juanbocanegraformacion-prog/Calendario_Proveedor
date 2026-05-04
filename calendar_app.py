import streamlit as st
import pandas as pd
import requests
import io
import sqlite3
import json
from datetime import datetime, timedelta
import streamlit.components.v1 as components

# ------------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA
# ------------------------------------------------------------
st.set_page_config(page_title="Monitor ODC - RIOMARKET", layout="wide")

# ------------------------------------------------------------
# BASE DE DATOS (SQLite) - Persistencia Mejorada
# ------------------------------------------------------------
def init_db():
    conn = sqlite3.connect('calendario.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS proveedores_maestro
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       nombre TEXT, 
                       comprador_habitual TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS calendario_historico
                      (id INTEGER PRIMARY KEY, 
                       fecha_semana TEXT, 
                       dia_semana TEXT, 
                       proveedores TEXT)''')
    try:
        cursor.execute('''CREATE UNIQUE INDEX idx_fecha_dia ON calendario_historico (fecha_semana, dia_semana)''')
    except sqlite3.OperationalError:
        pass 
    conn.commit()
    conn.close()

init_db()

# ------------------------------------------------------------
# AUTENTICACIÓN
# ------------------------------------------------------------
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.title("Inicio de sesión requerido")
    with st.form("login_form"):
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Acceder")
        if submitted:
            if password == "RioMarket2026":
                st.session_state.autenticado = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta")
    st.stop()

# ------------------------------------------------------------
# FUNCIONES DE LÓGICA
# ------------------------------------------------------------
dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

def cargar_semana(fecha_consulta):
    conn = sqlite3.connect('calendario.db')
    fecha_str = str(fecha_consulta)
    df = pd.read_sql_query(
        "SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?",
        conn, params=(fecha_str,)
    )

    def split_prov_safe(s):
        if not s: return []
        return [p.strip() for p in s.split('|') if p.strip()]

    if not df.empty:
        res = dict(zip(df['dia_semana'], df['proveedores'].apply(split_prov_safe)))
        conn.close()
        return res

    # Si no hay datos, buscar la última semana planificada para clonar
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(fecha_semana) FROM calendario_historico WHERE fecha_semana < ?", (fecha_str,))
    ultima = cursor.fetchone()
    if ultima and ultima[0]:
        df_h = pd.read_sql_query(
            "SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?",
            conn, params=(ultima[0],)
        )
        conn.close()
        return dict(zip(df_h['dia_semana'], df_h['proveedores'].apply(split_prov_safe)))

    conn.close()
    return {d: [] for d in dias_semana}

def guardar_calendario(fecha, calendario_dict):
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    for dia, lista_provs in calendario_dict.items():
        provs_str = "|".join([p.strip().upper() for p in lista_provs if p.strip()])
        cursor.execute(
            "INSERT OR REPLACE INTO calendario_historico (fecha_semana, dia_semana, proveedores) VALUES (?, ?, ?)",
            (str(fecha), dia, provs_str)
        )
    conn.commit()
    conn.close()

def obtener_compradores_autorizados():
    conn = sqlite3.connect('calendario.db')
    df = pd.read_sql_query("SELECT id, nombre, comprador_habitual FROM proveedores_maestro", conn)
    conn.close()
    return df

def obtener_proveedores_registrados():
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT nombre FROM proveedores_maestro ORDER BY nombre")
    provs = [row[0] for row in cursor.fetchall()]
    conn.close()
    return provs

# ------------------------------------------------------------
# GESTIÓN DE FECHAS (sesión)
# ------------------------------------------------------------
if 'fecha_referencia' not in st.session_state:
    hoy = datetime.now()
    st.session_state.fecha_referencia = (hoy - timedelta(days=hoy.weekday())).date()

# ------------------------------------------------------------
# SIDEBAR
# ------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Configuración")

    with st.expander("📅 Planificación Semanal", expanded=True):
        dia_edit = st.selectbox("Día a editar:", dias_semana)
        cal_actual = cargar_semana(st.session_state.fecha_referencia)
        provs_registrados = obtener_proveedores_registrados()
        
        if not provs_registrados:
            st.warning("Registre proveedores primero.")
        else:
            seleccion_actual = [p for p in cal_actual.get(dia_edit, []) if p in provs_registrados]
            nuevos_seleccionados = st.multiselect(
                "Proveedores:", options=provs_registrados, default=seleccion_actual
            )
            if st.button("💾 Guardar Plan"):
                cal_actual[dia_edit] = [p.strip().upper() for p in nuevos_seleccionados]
                guardar_calendario(st.session_state.fecha_referencia, cal_actual)
                st.success("Guardado.")
                st.rerun()

    with st.expander("👤 Registro Maestro"):
        new_p = st.text_input("Proveedor:").upper()
        new_c = st.text_input("Comprador:").upper()
        if st.button("➕ Agregar"):
            if new_p and new_c:
                conn = sqlite3.connect('calendario.db')
                conn.execute("INSERT INTO proveedores_maestro (nombre, comprador_habitual) VALUES (?, ?)", (new_p, new_c))
                conn.commit()
                conn.close()
                st.rerun()

# ------------------------------------------------------------
# ÁREA PRINCIPAL
# ------------------------------------------------------------
st.title("📅 Monitor de Órdenes de Compra")

col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])
with col_nav1:
    if st.button("⬅️ Anterior"):
        st.session_state.fecha_referencia -= timedelta(days=7)
        st.rerun()
with col_nav3:
    if st.button("Siguiente ➡️"):
        st.session_state.fecha_referencia += timedelta(days=7)
        st.rerun()

st.markdown(f"### Semana del {st.session_state.fecha_referencia.strftime('%d/%m/%Y')}")
cal_data = cargar_semana(st.session_state.fecha_referencia)

# Visualización de tabla
df_vis = pd.DataFrame.from_dict(cal_data, orient='index').transpose().fillna("-")
st.dataframe(df_vis[dias_semana], use_container_width=True, hide_index=True)

st.divider()

# ------------------------------------------------------------
# SISTEMA DE MONITOREO (CARRUSEL)
# ------------------------------------------------------------
st.subheader("🤖 Monitoreo de Registros")

# Lógica para evitar que los registros "desaparezcan" al cambiar de día
es_semana_actual = st.session_state.fecha_referencia == (datetime.now() - timedelta(days=datetime.now().weekday())).date()

if es_semana_actual:
    dia_actual_nombre = dias_semana[datetime.now().weekday()]
    dia_monitoreo = st.selectbox("Filtrar por día:", dias_semana, index=datetime.now().weekday())
else:
    dia_monitoreo = st.selectbox("Seleccione día de esta semana para ver registros:", dias_semana)

provs_hoy = cal_data.get(dia_monitoreo, [])

if not provs_hoy:
    st.info(f"No hay proveedores planificados para el {dia_monitoreo}.")
else:
    url = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/ODC_alerta.xlsx"
    try:
        res = requests.get(url)
        df_raw = pd.read_excel(io.BytesIO(res.content))
        df_raw.columns = df_raw.columns.str.strip()
        df_raw = df_raw.rename(columns={'Creado por': 'Comprador', 'Sucursal destino': 'SucursalDestino'})

        df_aut = obtener_compradores_autorizados()
        if not df_aut.empty:
            df_aut['key'] = df_aut['nombre'].str.strip().upper() + "|" + df_aut['comprador_habitual'].str.strip().upper()
            set_aut = set(df_aut['key'].tolist())
            
            proveedores_upper = [p.strip().upper() for p in provs_hoy]

            def validar(row):
                p = str(row['Proveedor']).strip().upper()
                c = str(row['Comprador']).strip().upper()
                return (p in proveedores_upper) and (f"{p}|{c}" in set_aut)

            df_f = df_raw[df_raw.apply(validar, axis=1)].copy()

            if not df_f.empty:
                ordenes = []
                for _, row in df_f.iterrows():
                    ordenes.append({
                        'numero': str(row['Número de orden'])[-19:],
                        'proveedor': row['Proveedor'],
                        'comprador': row['Comprador'],
                        'sucursal': row['SucursalDestino']
                    })

                ordenes_json = json.dumps(ordenes)
                
                carrusel_html = f"""
                <div id="carousel-container" style="background:#fff; border:5px solid #2E7D32; border-radius:20px; padding:40px; text-align:center; font-family:sans-serif;">
                    <div style="font-size:2rem; color:#2E7D32; font-weight:bold;">ORDEN DE COMPRA</div>
                    <div id="ord-num" style="font-size:6rem; color:#1B5E20; font-weight:900;">#---</div>
                    <div id="ord-prov" style="font-size:2rem; font-weight:bold; color:#333;">---</div>
                    <div id="ord-comp" style="font-size:1.5rem; color:#444; margin-top:10px;">---</div>
                    <div id="ord-suc" style="font-size:1.5rem; color:#444;">---</div>
                </div>
                <script>
                    const orders = {ordenes_json};
                    let idx = 0;
                    function update() {{
                        const o = orders[idx];
                        document.getElementById('ord-num').textContent = '#' + o.numero;
                        document.getElementById('ord-prov').textContent = o.proveedor;
                        document.getElementById('ord-comp').textContent = 'Comprador: ' + o.comprador;
                        document.getElementById('ord-suc').textContent = 'Destino: ' + o.sucursal;
                        idx = (idx + 1) % orders.length;
                    }}
                    update();
                    setInterval(update, 6000);
                </script>
                """
                components.html(carrusel_html, height=450)
                st.caption(f"🔄 Rotando {len(ordenes)} órdenes validadas.")
            else:
                st.warning("No se encontraron órdenes en el Excel que coincidan con la planificación de este día.")
    except Exception as e:
        st.error(f"Error de conexión: {e}")
