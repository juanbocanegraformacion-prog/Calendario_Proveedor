import streamlit as st
import pandas as pd
import requests
import io
import sqlite3
from datetime import datetime, timedelta

# ------------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA
# ------------------------------------------------------------
st.set_page_config(page_title="Monitor ODC - RIOMARKET", layout="wide")

# ------------------------------------------------------------
# BASE DE DATOS SQLITE (INICIALIZACIÓN)
# ------------------------------------------------------------
DB_FILE = "calendario.db"

def init_db():
    """Crea las tablas si no existen."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Tabla maestra de proveedores
    c.execute('''
        CREATE TABLE IF NOT EXISTS proveedores_maestro (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            comprador_habitual TEXT
        )
    ''')
    # Tabla histórica del calendario semanal
    c.execute('''
        CREATE TABLE IF NOT EXISTS calendario_historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_semana DATE NOT NULL,      -- fecha de inicio de la semana (lunes)
            dia_semana TEXT NOT NULL,        -- Lunes, Martes, etc.
            proveedor_id INTEGER NOT NULL,
            FOREIGN KEY (proveedor_id) REFERENCES proveedores_maestro (id)
        )
    ''')
    conn.commit()
    conn.close()

def obtener_proveedores_maestro():
    """Retorna un DataFrame con todos los proveedores registrados."""
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT id, nombre, comprador_habitual FROM proveedores_maestro", conn)
    conn.close()
    return df

def guardar_proveedor(nombre, comprador=None):
    """Inserta un proveedor en la tabla maestra si no existe."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO proveedores_maestro (nombre, comprador_habitual) VALUES (?, ?)", (nombre, comprador))
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # ya existe
    conn.close()

def obtener_id_proveedor(nombre):
    """Obtiene el id de un proveedor por su nombre exacto."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id FROM proveedores_maestro WHERE nombre = ?", (nombre,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def guardar_calendario_semana(fecha_lunes, dia_semana, proveedores_lista):
    if isinstance(fecha_lunes, datetime):
        fecha_str = fecha_lunes.date().isoformat()
    elif hasattr(fecha_lunes, 'isoformat'):
        fecha_str = fecha_lunes.isoformat()
    else:
        fecha_str = str(fecha_lunes)
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM calendario_historico WHERE fecha_semana = ? AND dia_semana = ?", (fecha_str, dia_semana))
    for nombre_prov in proveedores_lista:
        nombre_prov = nombre_prov.strip()
        if not nombre_prov:
            continue
        guardar_proveedor(nombre_prov)
        prov_id = obtener_id_proveedor(nombre_prov)
        if prov_id:
            c.execute("INSERT INTO calendario_historico (fecha_semana, dia_semana, proveedor_id) VALUES (?, ?, ?)",
                      (fecha_str, dia_semana, prov_id))
    conn.commit()
    conn.close()

def cargar_calendario_semana(fecha_lunes):
    """
    Retorna un diccionario {dia: [lista de proveedores]} para una semana dada.
    Si no hay datos, retorna un diccionario vacío con días en blanco.
    """
    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    calendario = {dia: [] for dia in dias}
    conn = sqlite3.connect(DB_FILE)
    query = """
        SELECT ch.dia_semana, pm.nombre
        FROM calendario_historico ch
        JOIN proveedores_maestro pm ON ch.proveedor_id = pm.id
        WHERE ch.fecha_semana = ?
        ORDER BY ch.dia_semana, pm.nombre
    """
    df = pd.read_sql_query(query, conn, params=(fecha_lunes,))
    conn.close()
    if not df.empty:
        for dia in dias:
            provs = df[df['dia_semana'] == dia]['nombre'].tolist()
            calendario[dia] = provs
    return calendario

def obtener_semanas_disponibles():
    """Retorna una lista de fechas de inicio de semana (lunes) con datos en la BD."""
    conn = sqlite3.connect(DB_FILE)
    query = "SELECT DISTINCT fecha_semana FROM calendario_historico ORDER BY fecha_semana DESC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df['fecha_semana'].tolist() if not df.empty else []

# Inicializar BD
init_db()

# ------------------------------------------------------------
# FUNCIONES AUXILIARES DE FECHAS
# ------------------------------------------------------------
def obtener_lunes_de_semana(fecha=None):
    """Devuelve la fecha del lunes de la semana que contiene a 'fecha' (hoy por defecto)."""
    if fecha is None:
        fecha = datetime.now().date()
    lunes = fecha - timedelta(days=fecha.weekday())
    return lunes

def formatear_rango_semana(lunes):
    """Retorna string 'Semana XX (DD-MMM al DD-MMM)'."""
    fin = lunes + timedelta(days=6)
    num_semana = lunes.isocalendar()[1]
    return f"Semana {num_semana} ({lunes.strftime('%d-%b')} al {fin.strftime('%d-%b')})"

# ------------------------------------------------------------
# INTERFAZ PRINCIPAL
# ------------------------------------------------------------
def main():
    st.title("📅 Gestión de Calendario de Proveedores")
    st.markdown("### Configuración de Monitoreo Semanal")

    # ---------- SIDEBAR: PANEL DE CONTROL ----------
    with st.sidebar:
        st.header("⚙️ Panel de Control")
        dia_editar = st.selectbox("Seleccionar día para editar:",
                                  ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"])
        # Obtener proveedores actuales para el día seleccionado (según semana visualizada)
        # Necesitamos acceder al estado de la semana actual (que está en session_state)
        # Para facilitar, trabajaremos con el estado cargado de la semana activa.
        # Actualizaremos el text_area con los valores actuales.
        proveedores_actuales = st.session_state.get("calendario_actual", {}).get(dia_editar, [])
        nuevos_provs = st.text_area(f"Proveedores para {dia_editar}:",
                                    value=", ".join(proveedores_actuales))
        if st.button("💾 Guardar en BD (semana actual)"):
            # Parsear entrada
            lista_provs = [p.strip() for p in nuevos_provs.split(",") if p.strip()]
            # Actualizar en session_state
            st.session_state.calendario_actual[dia_editar] = lista_provs
            # Guardar en BD
            lunes_actual = st.session_state.get("semana_actual_lunes", obtener_lunes_de_semana())
            guardar_calendario_semana(lunes_actual, dia_editar, lista_provs)
            st.success(f"Calendario de {dia_editar} guardado en BD.")
            st.rerun()

        st.divider()
        st.subheader("📂 Semanas anteriores")
        semanas_bd = obtener_semanas_disponibles()
        if semanas_bd:
            # Convertir a string legible
            opciones = {formatear_rango_semana(pd.to_datetime(f)): f for f in semanas_bd}
            semana_seleccionada_str = st.selectbox("Seleccionar semana histórica:", list(opciones.keys()))
            if st.button("Cargar semana seleccionada"):
                fecha_lunes = opciones[semana_seleccionada_str]
                st.session_state.semana_actual_lunes = pd.to_datetime(fecha_lunes).date()
                st.session_state.calendario_actual = cargar_calendario_semana(st.session_state.semana_actual_lunes)
                st.rerun()
        else:
            st.info("No hay semanas históricas aún.")

    # ---------- ÁREA PRINCIPAL: VISUALIZACIÓN DE CALENDARIO ----------
    # Inicializar estado de semana actual
    if "semana_actual_lunes" not in st.session_state:
        st.session_state.semana_actual_lunes = obtener_lunes_de_semana()
    if "calendario_actual" not in st.session_state:
        st.session_state.calendario_actual = cargar_calendario_semana(st.session_state.semana_actual_lunes)

    lunes_actual = st.session_state.semana_actual_lunes
    calendario_vista = st.session_state.calendario_actual

    # Selector de semana con indicadores de historial (simplificado)
    col_sem1, col_sem2, col_sem3 = st.columns([1, 3, 1])
    with col_sem1:
        if st.button("◀ Semana anterior"):
            nuevo_lunes = lunes_actual - timedelta(days=7)
            st.session_state.semana_actual_lunes = nuevo_lunes
            st.session_state.calendario_actual = cargar_calendario_semana(nuevo_lunes)
            st.rerun()
    with col_sem2:
        st.markdown(f"### {formatear_rango_semana(lunes_actual)}")
        # Indicadores visuales (simulado: si hay datos en BD para esta semana, verde; si no, gris)
        tiene_datos = any(calendario_vista[dia] for dia in calendario_vista)
        color = "🟢" if tiene_datos else "⚪"
        st.caption(f"{color} Estado de monitoreo")
    with col_sem3:
        if st.button("Semana siguiente ▶"):
            nuevo_lunes = lunes_actual + timedelta(days=7)
            st.session_state.semana_actual_lunes = nuevo_lunes
            st.session_state.calendario_actual = cargar_calendario_semana(nuevo_lunes)
            st.rerun()

    st.subheader("📋 Vista de Planificación (Editable)")

    # Convertir calendario a DataFrame para data_editor
    # Queremos que sea una tabla con días como columnas
    # Vamos a construir un DataFrame con una fila por "Línea" (ficticia), o simplemente un editor de una sola fila con múltiples celdas.
    # Para simplificar y mantener compatibilidad, usaremos un formato donde cada día es una columna y la fila es única.
    # Pero data_editor permite editar listas en celdas. Aquí optaremos por un editor de tipo "lista de proveedores" por celda.
    df_plan = pd.DataFrame([calendario_vista])
    # Reordenar columnas para que coincida con días de semana
    dias_orden = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    df_plan = df_plan[dias_orden]

    # Usar st.data_editor para permitir edición directa
    edited_df = st.data_editor(
        df_plan,
        column_config={
            dia: st.column_config.ListColumn(
                dia,
                help="Ingrese proveedores separados por coma"
            ) for dia in dias_orden
        },
        use_container_width=True,
        num_rows="fixed",
        key="editor_calendario"
    )

    # Botón para aplicar cambios del editor a BD y session_state
    if st.button("💾 Guardar cambios del editor (toda la semana)"):
        # Actualizar session_state con los valores editados
        for dia in dias_orden:
            nueva_lista = edited_df.at[0, dia]
            if isinstance(nueva_lista, str):
                nueva_lista = [p.strip() for p in nueva_lista.split(",") if p.strip()]
            st.session_state.calendario_actual[dia] = nueva_lista
            guardar_calendario_semana(lunes_actual, dia, nueva_lista)
        st.success("Calendario completo guardado en BD.")
        st.rerun()

    st.divider()

    # ---------- SECCIÓN RPA ----------
    st.subheader("🤖 Ejecución de RPA")
    sucursal_target = st.selectbox("Sucursal a monitorear:", ["CENDI GUATIRE", "CENDI 4 DE MAYO"])

    col_btn1, col_btn2 = st.columns(2)

    if col_btn1.button("🚀 Iniciar Monitoreo de Hoy", type="primary"):
        # Determinar día actual
        dia_hoy = datetime.now().strftime('%A')
        mapping = {
            "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
            "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
        }
        dia_es = mapping.get(dia_hoy)
        provs_hoy = st.session_state.calendario_actual.get(dia_es, [])

        if not provs_hoy:
            st.error(f"No hay proveedores programados para hoy ({dia_es}).")
        else:
            st.info(f"Buscando órdenes para: {', '.join(provs_hoy)}")
            url_github = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/%C3%93rdenes%20de%20compra%2016_04_2026.xlsx"

            try:
                response = requests.get(url_github)
                if response.status_code == 200:
                    excel_data = io.BytesIO(response.content)
                    df = pd.read_excel(excel_data, engine='openpyxl')
                    df.columns = df.columns.str.strip()

                    # Filtrar todas las órdenes de los proveedores del día
                    patrones = [p.strip().upper() for p in provs_hoy]
                    mask_global = df['Proveedor'].astype(str).str.upper().apply(
                        lambda x: any(patron in x for patron in patrones)
                    )
                    df_resultado = df[mask_global].copy()

                    if not df_resultado.empty:
                        # Seleccionar columnas requeridas
                        columnas_mostrar = ['Número de orden', 'Proveedor', 'Estatus',
                                            'Tipo de entrega', 'Tipo de distribución', 'Creado por']
                        df_final = df_resultado[columnas_mostrar].rename(columns={'Creado por': 'Comprador'})
                        st.subheader("📊 Órdenes de Compra - Resultados del Día")
                        st.dataframe(
                            df_final,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Número de orden": st.column_config.TextColumn("N° Orden"),
                                "Comprador": st.column_config.TextColumn("Comprador Asignado")
                            }
                        )
                    else:
                        st.info("✅ No se encontraron órdenes activas para los proveedores de hoy.")
                else:
                    st.error(f"Error al descargar reporte de GitHub (Status {response.status_code})")
            except Exception as e:
                st.error(f"Error técnico: {e}")

    if col_btn2.button("📊 Ver Reporte Completo"):
        url_github = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/%C3%93rdenes%20de%20compra%2016_04_2026.xlsx"
        try:
            res = requests.get(url_github)
            df_full = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
            st.dataframe(df_full)
        except Exception as e:
            st.error(f"No se pudo cargar el reporte: {e}")

if __name__ == "__main__":
    main()
