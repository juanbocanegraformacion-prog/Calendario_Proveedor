import streamlit as st
import pandas as pd
import requests
import io
import sqlite3
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# ------------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA
# ------------------------------------------------------------
st.set_page_config(page_title="Monitor ODC - RIOMARKET", layout="wide")

# ------------------------------------------------------------
# CSS PERSONALIZADO (Cola anterior + nuevo Carrousel)
# ------------------------------------------------------------
st.markdown(
    """
<style>
    /* Estilo del carrusel: fondo blanco, bordes verdes gruesos, sombra 3D */
    .carousel-card {
        background-color: #FFFFFF;
        border: 5px solid #2E7D32;
        border-radius: 20px;
        box-shadow: 0 8px 16px rgba(0,0,0,0.25), 0 12px 40px rgba(0,0,0,0.15);
        padding: 40px;
        text-align: center;
        margin: 20px auto;
        width: 70%;
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
    /* Opcional: mantener el estilo de cola anterior (por si se necesita más adelante) */
    .main-order-container {
        background-color: #FFC107;
        color: black;
        border-radius: 15px;
        padding: 30px;
        text-align: center;
        border: 5px solid #E67E22;
        margin-bottom: 20px;
    }
    .main-order-title { font-size: 1.8rem; font-weight: bold; }
    .main-order-number { font-size: 7rem; font-weight: 900; line-height: 1; margin: 10px 0; }
    .main-order-info { font-size: 1.4rem; font-weight: bold; }
    
    .queue-card {
        background-color: #262730;
        color: white;
        border-radius: 10px;
        padding: 12px;
        margin-bottom: 10px;
        border-left: 8px solid #FFC107;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .queue-number { font-size: 1.8rem; font-weight: bold; color: #FFC107; }
    .queue-details { text-align: right; font-size: 0.85rem; }
</style>
""",
    unsafe_allow_html=True
)

# ------------------------------------------------------------
# VARIABLES GLOBALES
# ------------------------------------------------------------
dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

# ------------------------------------------------------------
# BASE DE DATOS (SQLite) - Definiciones completas
# ------------------------------------------------------------
def init_db():
    """Crea las tablas necesarias si no existen."""
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS proveedores_maestro (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            comprador_habitual TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS calendario_historico (
            id INTEGER PRIMARY KEY,
            fecha_semana TEXT,
            dia_semana TEXT,
            proveedores TEXT
        )
    ''')
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_fecha_dia 
        ON calendario_historico (fecha_semana, dia_semana)
    ''')
    conn.commit()
    conn.close()

def forzar_reset_maestro():
    """Elimina y recrea la tabla de proveedores maestro."""
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS proveedores_maestro")
    conn.commit()
    conn.close()
    st.cache_data.clear()
    init_db()

# Inicializar base de datos al importar el módulo
init_db()

def cargar_semana(fecha_consulta):
    """
    Carga los proveedores de la semana correspondiente a 'fecha_consulta'.
    Si no existe, hereda los de la semana anterior más reciente.
    """
    conn = sqlite3.connect('calendario.db')
    fecha_str = str(fecha_consulta)
    df = pd.read_sql_query(
        "SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?",
        conn,
        params=(fecha_str,)
    )
    if not df.empty:
        res = dict(zip(df['dia_semana'], df['proveedores'].apply(lambda x: x.split(',') if x else [])))
        conn.close()
        return res

    # Herencia: tomar la semana más reciente anterior a la fecha solicitada
    cursor = conn.cursor()
    cursor.execute(
        "SELECT MAX(fecha_semana) FROM calendario_historico WHERE fecha_semana < ?",
        (fecha_str,)
    )
    ultima = cursor.fetchone()
    if ultima and ultima[0]:
        df_h = pd.read_sql_query(
            "SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?",
            conn,
            params=(ultima[0],)
        )
        conn.close()
        return dict(zip(df_h['dia_semana'], df_h['proveedores'].apply(lambda x: x.split(',') if x else [])))

    conn.close()
    # Si no hay ninguna semana anterior, devolver listas vacías
    return {d: [] for d in dias_semana}

def guardar_calendario(fecha, calendario_dict):
    """Persiste en la BD la planificación de una semana completa."""
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
    """Inserta un proveedor y su comprador habitual. Retorna True si es nuevo."""
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    p_up, c_up = proveedor.strip().upper(), comprador.strip().upper()
    try:
        cursor.execute(
            "SELECT 1 FROM proveedores_maestro WHERE nombre = ? AND comprador_habitual = ?",
            (p_up, c_up)
        )
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO proveedores_maestro (nombre, comprador_habitual) VALUES (?, ?)",
                (p_up, c_up)
            )
            conn.commit()
            conn.close()
            return True
    except sqlite3.IntegrityError:
        pass
    conn.close()
    return False

def eliminar_comprador(id_registro):
    """Elimina un registro del maestro de compradores por su ID."""
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM proveedores_maestro WHERE id = ?", (id_registro,))
    conn.commit()
    conn.close()

def obtener_compradores_autorizados():
    """Devuelve un DataFrame con los registros del maestro de compradores."""
    conn = sqlite3.connect('calendario.db')
    df = pd.read_sql_query("SELECT id, nombre, comprador_habitual FROM proveedores_maestro", conn)
    conn.close()
    return df

# ------------------------------------------------------------
# GESTIÓN DE FECHAS (sesión)
# ------------------------------------------------------------
if 'fecha_referencia' not in st.session_state:
    hoy = datetime.now()
    # Lunes de la semana actual
    st.session_state.fecha_referencia = (hoy - timedelta(days=hoy.weekday())).date()

if 'carousel_index' not in st.session_state:
    st.session_state.carousel_index = 0

# ------------------------------------------------------------
# SIDEBAR - Rediseño limpio y ordenado
# ------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Panel de Configuración")

    # --- Sección expandible: Planificación Semanal ---
    with st.expander("📅 Planificación Semanal", expanded=True):
        dia_edit = st.selectbox("Día a editar:", dias_semana)
        cal_actual = cargar_semana(st.session_state.fecha_referencia)
        provs_input = st.text_area(
            "Proveedores (separados por coma):",
            value=", ".join(cal_actual.get(dia_edit, []))
        )

        if st.button("💾 Guardar planificación"):
            cal_actual[dia_edit] = [
                p.strip().upper() for p in provs_input.split(",") if p.strip()
            ]
            guardar_calendario(st.session_state.fecha_referencia, cal_actual)
            st.success("Planificación actualizada.")
            st.rerun()

    # --- Sección expandible: Registro Maestro de Compradores ---
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
            # Editor interactivo de la tabla
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

            # Eliminación por ID
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

    # --- Sección expandible: Zona de Peligro ---
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

# Navegación de semanas
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
# SISTEMA CARRUSEL (Monitoreo en Tiempo Real)
# ------------------------------------------------------------
st.subheader("🤖 Monitoreo en Tiempo Real")

# Auto-refresco cada 6 segundos
st_autorefresh(interval=6000, limit=None, key="carousel_refresh")

dia_hoy_es = dias_semana[datetime.now().weekday()]
provs_hoy = cal_data.get(dia_hoy_es, [])

if not provs_hoy:
    st.info(f"Hoy ({dia_hoy_es}) no hay proveedores planificados.")
else:
    url = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/ODC_alerta.xlsx"
    try:
        res = requests.get(url)
        df_raw = pd.read_excel(io.BytesIO(res.content))
        # Limpieza de nombres de columnas
        df_raw.columns = df_raw.columns.str.strip()
        df_raw = df_raw.rename(columns={'Creado por': 'Comprador'})

        # Cargar pares autorizados
        df_aut = obtener_compradores_autorizados()
        df_aut['key'] = (
            df_aut['nombre'].str.upper().str.strip() + "|" +
            df_aut['comprador_habitual'].str.upper().str.strip()
        )
        set_aut = set(df_aut['key'].tolist())

        # Filtrar órdenes: proveedor está en la lista de hoy & par autorizado
        def validar(row):
            p = str(row['Proveedor']).upper().strip()
            c = str(row['Comprador']).upper().strip()
            # Proveedor debe estar exactamente en la lista de hoy
            if p not in [prov.upper() for prov in provs_hoy]:
                return False
            return f"{p}|{c}" in set_aut

        df_f = df_raw[df_raw.apply(validar, axis=1)].copy()

        if not df_f.empty:
            ordenes = df_f.to_dict('records')
            # Avanzar índice del carrusel
            indice = st.session_state.carousel_index % len(ordenes)
            orden_actual = ordenes[indice]

            # Mostrar tarjeta de carrusel grande
            st.markdown(f"""
                <div class="carousel-card">
                    <div class="carousel-title">ORDEN DE COMPRA ACTIVA</div>
                    <div class="carousel-order-number">#{str(orden_actual['Número de orden'])[-4:]}</div>
                    <div class="carousel-info">{orden_actual['Proveedor']}</div>
                    <div class="carousel-detail">
                        Comprador: {orden_actual['Comprador']}
                    </div>
                </div>
            """, unsafe_allow_html=True)

            # Preparar el siguiente índice
            st.session_state.carousel_index = (indice + 1) % len(ordenes)
        else:
            st.info("Buscando órdenes validadas... (ninguna coincide aún)")
    except Exception as e:
        st.error(f"Error en la sincronización: {e}")
