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
# CSS PERSONALIZADO
# ------------------------------------------------------------
st.markdown("""
<style>
    .carousel-card {
        background-color: #FFFFFF;
        border: 5px solid #2E7D32;
        border-radius: 20px;
        box-shadow: 0 8px 16px rgba(0,0,0,0.25), 0 12px 40px rgba(0,0,0,0.15);
        padding: 40px;
        text-align: center;
        margin: 20px auto;
        width: 100%;
    }
    .carousel-title {
        font-size: 2rem;
        font-weight: bold;
        color: #2E7D32;
        margin-bottom: 15px;
    }
    .carousel-order-number {
        font-size: 8rem;
        font-weight: 900;
        color: #1B5E20;
        line-height: 1;
    }
    .carousel-info {
        font-size: 2rem;
        font-weight: bold;
        color: #333;
    }
    .carousel-detail {
        font-size: 1.5rem;
        color: #555;
        margin-top: 10px;
    }
    .missing-panel {
        background-color: #f9f9f9;
        border: 2px solid #e0e0e0;
        border-radius: 10px;
        padding: 15px;
        margin-top: 20px;
    }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------
# VARIABLES GLOBALES
# ------------------------------------------------------------
dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

# ------------------------------------------------------------
# BASE DE DATOS (SQLite)
# ------------------------------------------------------------
def init_db():
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS proveedores_maestro
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, comprador_habitual TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS calendario_historico
                      (id INTEGER PRIMARY KEY, fecha_semana TEXT, dia_semana TEXT, proveedores TEXT)''')
    cursor.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_fecha_dia
                      ON calendario_historico (fecha_semana, dia_semana)''')
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

init_db()

def cargar_semana(fecha_consulta):
    conn = sqlite3.connect('calendario.db')
    fecha_str = str(fecha_consulta)
    df = pd.read_sql_query(
        "SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?",
        conn, params=(fecha_str,)
    )
    if not df.empty:
        res = dict(zip(df['dia_semana'], df['proveedores'].apply(lambda x: x.split('/') if x else [])))
        conn.close()
        return res

    cursor = conn.cursor()
    cursor.execute("SELECT MAX(fecha_semana) FROM calendario_historico WHERE fecha_semana < ?", (fecha_str,))
    ultima = cursor.fetchone()
    if ultima and ultima[0]:
        df_h = pd.read_sql_query(
            "SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?",
            conn, params=(ultima[0],)
        )
        conn.close()
        return dict(zip(df_h['dia_semana'], df_h['proveedores'].apply(lambda x: x.split('/') if x else [])))

    conn.close()
    return {d: [] for d in dias_semana}

def guardar_calendario(fecha, calendario_dict):
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    for dia, lista_provs in calendario_dict.items():
        provs_str = ",".join([p.strip().upper() for p in lista_provs if p.strip()])
        cursor.execute(
            "INSERT OR REPLACE INTO calendario_historico (fecha_semana, dia_semana, proveedores) VALUES (?, ?, ?)",
            (str(fecha), dia, provs_str)
        )
    conn.commit()
    conn.close()

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
        pass
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

def obtener_proveedores_registrados():
    """Devuelve una lista con los nombres únicos de proveedores registrados en el maestro."""
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
    st.header("⚙️ Panel de Configuración")

    with st.expander("📅 Planificación Semanal", expanded=True):
        dia_edit = st.selectbox("Día a editar:", dias_semana)
        cal_actual = cargar_semana(st.session_state.fecha_referencia)
        # Obtener proveedores registrados para el dropdown
        provs_registrados = obtener_proveedores_registrados()
        if not provs_registrados:
            st.warning("No hay proveedores registrados aún. Agregue al menos uno en la sección 'Registro Maestro' primero.")
        else:
            # Proveedores actualmente seleccionados para este día (puede incluir algunos que ya no estén en el maestro)
            seleccion_actual = [p for p in cal_actual.get(dia_edit, []) if p in provs_registrados]
            nuevos_seleccionados = st.multiselect(
                "Proveedores para este día:",
                options=provs_registrados,
                default=seleccion_actual
            )
            if st.button("💾 Guardar planificación"):
                cal_actual[dia_edit] = [p.strip().upper() for p in nuevos_seleccionados]
                guardar_calendario(st.session_state.fecha_referencia, cal_actual)
                st.success("Planificación actualizada.")
                st.rerun()

    with st.expander("👤 Registro Maestro de Compradores"):
        st.caption("Agregar nuevo proveedor y su comprador habitual")
        new_p = st.text_input("Proveedor:", key="np")
        new_c = st.text_input("Comprador asignado:", key="nc")
        if st.button("➕ Registrar nuevo par"):
            if new_p and new_c:
                if registrar_comprador(new_p, new_c):
                    st.success(f"Registrado: {new_p.upper()} → {new_c.upper()}")
                else:
                    st.warning("Ese par ya existe.")
                st.rerun()
            else:
                st.error("Complete ambos campos.")
        st.divider()
        st.caption("Gestión de registros existentes")
        df_m = obtener_compradores_autorizados()
        if not df_m.empty:
            edited_m = st.data_editor(
                df_m,
                column_config={"id": None},
                hide_index=True,
                use_container_width=True,
                key="editor_compradores"
            )
            if st.button("🔄 Aplicar cambios de la tabla"):
                conn = sqlite3.connect('calendario.db')
                for _, row in edited_m.iterrows():
                    conn.execute(
                        "UPDATE proveedores_maestro SET nombre = ?, comprador_habitual = ? WHERE id = ?",
                        (row['nombre'].upper(), row['comprador_habitual'].upper(), row['id'])
                    )
                conn.commit()
                conn.close()
                st.success("Registros actualizados.")
                st.rerun()

            opciones_borrar = {
                row['id']: f"{row['nombre']} - ({row['comprador_habitual']})"
                for _, row in df_m.iterrows()
            }
            id_para_borrar = st.selectbox(
                "Eliminar par Proveedor-Comprador:",
                options=list(opciones_borrar.keys()),
                format_func=lambda x: opciones_borrar[x]
            )
            if st.button("🗑️ Eliminar seleccionado", type="primary"):
                eliminar_comprador(id_para_borrar)
                st.success("Eliminado.")
                st.rerun()
        else:
            st.info("No hay registros de compradores aún.")

    with st.expander("⚠️ Zona de Peligro"):
        if st.button("🔄 Reparar tabla de Proveedores (Reset)"):
            forzar_reset_maestro()
            st.warning("Tabla de proveedores reiniciada.")
            st.rerun()
        if st.button("💣 REINICIAR TODA LA BASE DE DATOS"):
            conn = sqlite3.connect('calendario.db')
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS proveedores_maestro")
            cursor.execute("DROP TABLE IF EXISTS calendario_historico")
            conn.commit()
            conn.close()
            init_db()
            st.warning("Base de datos completamente borrada y recreada.")
            st.rerun()

# ------------------------------------------------------------
# ÁREA PRINCIPAL
# ------------------------------------------------------------
st.title("📅 Monitor de Órdenes de Compra")

c1, c2, c3 = st.columns([1, 2, 1])
with c1:
    if st.button("⬅️ Semana anterior"):
        st.session_state.fecha_referencia -= timedelta(days=7)
        st.rerun()
with c3:
    if st.button("Semana siguiente ➡️"):
        st.session_state.fecha_referencia += timedelta(days=7)
        st.rerun()

st.markdown(f"### Semana del {st.session_state.fecha_referencia.strftime('%d/%m/%Y')}")
cal_data = cargar_semana(st.session_state.fecha_referencia)
df_visual = pd.DataFrame.from_dict(cal_data, orient='index').transpose().fillna("-")
st.dataframe(df_visual, use_container_width=True, hide_index=True)

st.divider()

# ------------------------------------------------------------
# SISTEMA CARRUSEL + PANEL DE FALTANTES
# ------------------------------------------------------------
st.subheader("🤖 Monitoreo en Tiempo Real")

dia_hoy_es = dias_semana[datetime.now().weekday()]
provs_hoy = cal_data.get(dia_hoy_es, [])

if not provs_hoy:
    st.info(f"Hoy ({dia_hoy_es}) no hay proveedores planificados.")
else:
    url = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/ODC_alerta.xlsx"
    try:
        res = requests.get(url)
        df_raw = pd.read_excel(io.BytesIO(res.content))
        df_raw.columns = df_raw.columns.str.strip()
        df_raw = df_raw.rename(columns={'Creado por': 'Comprador'})

        df_aut = obtener_compradores_autorizados()
        if df_aut.empty:
            st.warning("No hay pares Proveedor-Comprador registrados. Agréguelos en el panel lateral.")
        else:
            df_aut['key'] = (
                df_aut['nombre'].str.upper().str.strip() + "|" +
                df_aut['comprador_habitual'].str.upper().str.strip()
            )
            set_aut = set(df_aut['key'].tolist())
            proveedores_upper = [p.strip().upper() for p in provs_hoy]

            def validar(row):
                p = str(row['Proveedor']).upper().strip()
                c = str(row['Comprador']).upper().strip()
                if p not in proveedores_upper:
                    return False
                return f"{p}|{c}" in set_aut

            df_f = df_raw[df_raw.apply(validar, axis=1)].copy()

            # Pares registrados que están planificados para hoy
            pares_planificados = df_aut[df_aut['nombre'].isin(proveedores_upper)].copy()
            # Claves de las órdenes activas
            if not df_f.empty:
                set_activas = set(df_f['Proveedor'].str.upper() + "|" + df_f['Comprador'].str.upper())
            else:
                set_activas = set()

            pares_planificados['activo'] = pares_planificados['key'].isin(set_activas)
            pares_faltantes = pares_planificados[~pares_planificados['activo']][['nombre', 'comprador_habitual']]

            if not df_f.empty:
                # Dividir en dos columnas: carrusel y panel de faltantes
                col_izq, col_der = st.columns([3, 1])
                with col_izq:
                    # Carrusel
                    ordenes = []
                    for _, row in df_f.iterrows():
                        ordenes.append({
                            'numero': str(row['Número de orden'])[-4:],
                            'proveedor': row['Proveedor'],
                            'comprador': row['Comprador']
                        })
                    ordenes_json = json.dumps(ordenes)
                    carrusel_html = f"""
                    <style>
                    .carousel-card {{
                        background-color: #FFFFFF;
                        border: 5px solid #2E7D32;
                        border-radius: 20px;
                        box-shadow: 0 8px 16px rgba(0,0,0,0.25), 0 12px 40px rgba(0,0,0,0.15);
                        padding: 40px;
                        text-align: center;
                        margin: 20px auto;
                        width: 100%;
                    }}
                    .carousel-title {{
                        font-size: 2rem;
                        font-weight: bold;
                        color: #2E7D32;
                        margin-bottom: 15px;
                    }}
                    .carousel-order-number {{
                        font-size: 8rem;
                        font-weight: 900;
                        color: #1B5E20;
                        line-height: 1;
                    }}
                    .carousel-info {{
                        font-size: 2rem;
                        font-weight: bold;
                        color: #333;
                    }}
                    .carousel-detail {{
                        font-size: 1.5rem;
                        color: #555;
                        margin-top: 10px;
                    }}
                    </style>
                    <div id="carousel-container">
                        <div class="carousel-card">
                            <div class="carousel-title">ORDEN DE COMPRA ACTIVA</div>
                            <div class="carousel-order-number">#---</div>
                            <div class="carousel-info">Cargando...</div>
                            <div class="carousel-detail">Comprador: ---</div>
                        </div>
                    </div>
                    <script>
                    const orders = {ordenes_json};
                    let currentIndex = 0;
                    function showOrder(index) {{
                        const order = orders[index];
                        document.querySelector('#carousel-container .carousel-order-number').textContent = '#' + order.numero;
                        document.querySelector('#carousel-container .carousel-info').textContent = order.proveedor;
                        document.querySelector('#carousel-container .carousel-detail').textContent = 'Comprador: ' + order.comprador;
                    }}
                    showOrder(0);
                    setInterval(() => {{
                        currentIndex = (currentIndex + 1) % orders.length;
                        showOrder(currentIndex);
                    }}, 6000);
                    </script>
                    """
                    components.html(carrusel_html, height=450)
                    st.caption(f"🔄 {len(ordenes)} órdenes validadas rotando cada 6 segundos")

                with col_der:
                    st.markdown("### ⚠️ Sin órdenes")
                    if not pares_faltantes.empty:
                        st.dataframe(
                            pares_faltantes.rename(columns={'nombre': 'Proveedor', 'comprador_habitual': 'Comprador'}),
                            hide_index=True,
                            use_container_width=True
                        )
                    else:
                        st.success("Todos los pares tienen órdenes activas.")
            else:
                # No hay órdenes filtradas
                st.info("Buscando órdenes validadas... (ninguna coincide aún)")
                with st.expander("🔍 Ver diagnóstico de filtros"):
                    st.write("**Proveedores planificados para hoy:**", proveedores_upper)
                    st.write("**Pares Proveedor-Comprador registrados:**")
                    st.dataframe(df_aut[['nombre', 'comprador_habitual']].rename(columns={'nombre': 'Proveedor', 'comprador_habitual': 'Comprador'}))
                    st.caption("Asegúrese de que el nombre del proveedor en la planificación sea **exactamente igual** al que aparece en el archivo Excel (respetando comas, puntos, espacios).")
                if not pares_faltantes.empty:
                    st.markdown("---")
                    st.subheader("⚠️ Pares planificados sin órdenes")
                    st.dataframe(
                        pares_faltantes.rename(columns={'nombre': 'Proveedor', 'comprador_habitual': 'Comprador'}),
                        hide_index=True
                    )
    except Exception as e:
        st.error(f"Error en la sincronización: {e}")
