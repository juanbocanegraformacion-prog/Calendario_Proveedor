Para lograr que el monitoreo sea automático y se actualice sin necesidad de un botón, debemos encapsular la lógica de procesamiento en una función y llamarla directamente en el flujo principal de ejecución de Streamlit. 

Al eliminar el botón, cada vez que cambies de semana o agregues un comprador, Streamlit volverá a ejecutar el script y actualizará los resultados en tiempo real.

### Código Completo con Actualización Automática

```python
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

def obtener_compradores_autorizados():
    conn = sqlite3.connect('calendario.db')
    df = pd.read_sql_query("SELECT nombre, comprador_habitual FROM proveedores_maestro", conn)
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

def cargar_semana(fecha):
    conn = sqlite3.connect('calendario.db')
    df = pd.read_sql_query("SELECT dia_semana, proveedores FROM calendario_historico WHERE fecha_semana = ?", 
                           conn, params=(str(fecha),))
    conn.close()
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
    dia_edit = st.selectbox("Día:", ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"])
    cal_actual = cargar_semana(st.session_state.fecha_referencia) or {d: [] for d in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]}
    provs_input = st.text_area("Proveedores (sep. por coma):", value=", ".join(cal_actual.get(dia_edit, [])))

    st.divider()
    st.subheader("👤 Registro de Compradores")
    new_p = st.text_input("Proveedor:")
    new_c = st.text_input("Comprador:")
    
    if st.button("💾 Guardar Cambios"):
        cal_actual[dia_edit] = [p.strip().upper() for p in provs_input.split(",") if p.strip()]
        guardar_calendario(st.session_state.fecha_referencia, cal_actual)
        if new_p and new_c:
            registrar_comprador(new_p, new_c)
        st.rerun()

# --- 4. ÁREA PRINCIPAL ---
st.title("📅 Monitor de Órdenes de Compra")

c1, c2, c3 = st.columns([1,2,1])
with c1:
    if st.button("⬅️ Anterior"):
        st.session_state.fecha_referencia -= timedelta(days=7)
        st.rerun()
with c3:
    if st.button("Siguiente ➡️"):
        st.session_state.fecha_referencia += timedelta(days=7)
        st.rerun()

st.markdown(f"### Planificación Semana: {st.session_state.fecha_referencia}")
cal_data = cargar_semana(st.session_state.fecha_referencia) or {d: ["-"] for d in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]}
st.data_editor(pd.DataFrame.from_dict(cal_data, orient='index').transpose(), use_container_width=True, hide_index=True)

st.divider()

# --- 5. LÓGICA DE MONITOREO AUTOMÁTICO ---
st.subheader("🤖 Monitoreo en Tiempo Real")

# Se ejecuta automáticamente al cargar la página
dia_hoy_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"][datetime.now().weekday()]
provs_hoy = cal_actual.get(dia_hoy_es, [])

if not provs_hoy or provs_hoy == ["-"]:
    st.info(f"No hay proveedores programados para hoy ({dia_hoy_es}).")
else:
    # Usamos cache para no saturar GitHub con peticiones en cada pequeño cambio
    @st.cache_data(ttl=300) # Se actualiza cada 5 minutos
    def obtener_datos_github(url):
        res = requests.get(url)
        return pd.read_excel(io.BytesIO(res.content), engine='openpyxl')

    url_excel = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/%C3%93rdenes%20de%20compra%2016_04_2026.xlsx"
    
    try:
        df_raw = obtener_datos_github(url_excel)
        df_raw.columns = df_raw.columns.str.strip()
        df_raw = df_raw.rename(columns={'Creado por': 'Comprador'})

        df_aut = obtener_compradores_autorizados()
        df_aut['key'] = df_aut['nombre'].str.upper() + "|" + df_aut['comprador_habitual'].str.upper()
        set_autorizados = set(df_aut['key'].tolist())

        def validar(row):
            p_ex = str(row['Proveedor']).upper().strip()
            c_ex = str(row['Comprador']).upper().strip()
            if not any(p in p_ex for p in provs_hoy): return False
            return f"{p_ex}|{c_ex}" in set_autorizados

        df_filtrado = df_raw[df_raw.apply(validar, axis=1)].copy()

        if not df_filtrado.empty:
            st.success(f"Órdenes validadas encontradas para hoy ({dia_hoy_es}):")
            st.dataframe(df_filtrado[['Número de orden', 'Proveedor', 'Estatus', 'Comprador']], use_container_width=True, hide_index=True)
        else:
            st.info("✅ Sin órdenes que coincidan con los criterios de hoy.")
            
    except Exception as e:
        st.error(f"Error al sincronizar con GitHub: {e}")
```

### Sugerencias y Mejoras Aplicadas:

* **Uso de `st.cache_data`**: Al ser una actualización automática, Streamlit ejecutaría la descarga del Excel cada vez que muevas un mouse o escribas algo. He añadido un caché de **5 minutos** (`ttl=300`) para que la app sea fluida y no bloquee el sitio por exceso de peticiones.
* **Estado Silencioso**: He cambiado el `st.spinner` por una carga más sutil. Si no hay datos, muestra un `st.info` en lugar de una advertencia para que la interfaz se sienta más limpia.
* **Sincronización de Mayúsculas**: He reforzado el `.str.upper()` en la creación de la `key` de autorizados para evitar que un error de escritura en la base de datos rompa el monitoreo.
* **Flujo UX**: Al quitar el botón, el usuario percibe la herramienta como un "Dashboard" vivo. Esto es ideal para pantallas que se dejan abiertas para monitoreo constante.

¿Te gustaría que añadiera un temporizador visual que indique en cuánto tiempo se volverá a sincronizar el archivo de GitHub?
