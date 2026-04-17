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
    # Tabla Maestro: Aquí vive el registro oficial de Compradores
    cursor.execute('''CREATE TABLE IF NOT EXISTS proveedores_maestro 
                      (nombre TEXT PRIMARY KEY, comprador_habitual TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS calendario_historico 
                      (id INTEGER PRIMARY KEY, fecha_semana TEXT, dia_semana TEXT, proveedores TEXT)''')
    cursor.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_fecha_dia 
                      ON calendario_historico (fecha_semana, dia_semana)''')
    conn.commit()
    conn.close()

init_db()

def gestionar_maestro(nombre_prov, nombre_comp):
    conn = sqlite3.connect('calendario.db')
    cursor = conn.cursor()
    cursor.execute('''INSERT OR REPLACE INTO proveedores_maestro (nombre, comprador_habitual) 
                      VALUES (?, ?)''', (nombre_prov.upper(), nombre_comp.upper()))
    conn.commit()
    conn.close()

def obtener_maestro_dict():
    conn = sqlite3.connect('calendario.db')
    df = pd.read_sql_query("SELECT * FROM proveedores_maestro", conn)
    conn.close()
    # Retornamos un diccionario {PROVEEDOR: COMPRADOR} para búsqueda rápida
    return dict(zip(df['nombre'], df['comprador_habitual']))

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
    return dict(zip(df['dia_semana'], df['proveedores'].apply(lambda x: x.split(',') if x else []))) if not df.empty else None

# --- 2. LÓGICA DE FECHAS ---
if 'fecha_referencia' not in st.session_state:
    hoy = datetime.now()
    st.session_state.fecha_referencia = (hoy - timedelta(days=hoy.weekday())).date()

# --- 3. SIDEBAR: REGISTRO DE PROVEEDOR Y COMPRADOR ---
with st.sidebar:
    st.header("⚙️ Configuración")
    
    # --- SECCIÓN: EDICIÓN DE CALENDARIO ---
    st.subheader("📅 Planificación Semanal")
    dia_edit = st.selectbox("Día para editar:", ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"])
    cal_actual = cargar_semana(st.session_state.fecha_referencia) or {d: [] for d in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]}
    provs_input = st.text_area("Proveedores (separados por coma):", value=", ".join(cal_actual.get(dia_edit, [])))

    # --- SECCIÓN: REGISTRO DE COMPRADOR (DEBAJO DE PROVEEDOR) ---
    st.divider()
    st.subheader("👤 Registro de Compradores")
    st.caption("Asigna qué comprador debe evaluar cada proveedor.")
    
    maestro_prov = st.text_input("Nombre del Proveedor:", placeholder="Ej: POLAR")
    maestro_comp = st.text_input("Comprador Autorizado:", placeholder="Ej: JESÚS PÉREZ")
    
    if st.button("💾 Guardar Todo"):
        # Guardar Calendario
        cal_actual[dia_edit] = [p.strip().upper() for p in provs_input.split(",") if p.strip()]
        guardar_calendario(st.session_state.fecha_referencia, cal_actual)
        
        # Guardar Maestro de Comprador (si hay datos)
        if maestro_prov and maestro_comp:
            gestionar_maestro(maestro_prov, maestro_comp)
            st.success(f"Maestro actualizado: {maestro_prov} -> {maestro_comp}")
        
        st.success("Calendario actualizado.")
        st.rerun()

# --- 4. ÁREA PRINCIPAL ---
st.title("📅 Monitor de Órdenes de Compra")

# Tabla Maestra
cal_data = cargar_semana(st.session_state.fecha_referencia) or {d: ["-"] for d in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]}
st.data_editor(pd.DataFrame.from_dict(cal_data, orient='index').transpose(), use_container_width=True)

st.divider()

# --- 5. EJECUCIÓN RPA CON VALIDACIÓN DE COMPRADOR ---
st.subheader("🤖 Validación de Órdenes")

if st.button("🚀 Iniciar Monitoreo", type="primary"):
    dia_hoy = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"][datetime.now().weekday()]
    provs_hoy = cal_actual.get(dia_hoy, [])
    
    # Obtener el registro oficial de compradores desde la DB
    maestro_dict = obtener_maestro_dict()

    if not provs_hoy:
        st.warning("No hay proveedores para hoy.")
    else:
        with st.spinner("Validando contra base de datos..."):
            url = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/%C3%93rdenes%20de%20compra%2016_04_2026.xlsx"
            try:
                res = requests.get(url)
                df_raw = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
                df_raw.columns = df_raw.columns.str.strip()
                df_raw = df_raw.rename(columns={'Creado por': 'Comprador'})

                # --- LÓGICA DE FILTRADO CRÍTICA ---
                def validar_orden(row):
                    prov_excel = str(row['Proveedor']).upper().strip()
                    comp_excel = str(row['Comprador']).upper().strip()
                    
                    # 1. ¿El proveedor está en mi planificación de hoy?
                    if not any(p in prov_excel for p in provs_hoy):
                        return False
                    
                    # 2. ¿El comprador del excel coincide con mi registro oficial?
                    # Buscamos en el maestro cuál es el comprador asignado a este proveedor
                    comp_autorizado = maestro_dict.get(prov_excel)
                    
                    # Si el comprador coincide, permitimos la orden. Si no, se ignora.
                    return comp_excel == comp_autorizado

                # Aplicamos el filtro
                df_final = df_raw[df_raw.apply(validar_orden, axis=1)].copy()

                if not df_final.empty:
                    st.success(f"Se encontraron {len(df_final)} órdenes validadas.")
                    st.dataframe(df_final[['Número de orden', 'Proveedor', 'Estatus', 'Comprador']], use_container_width=True, hide_index=True)
                else:
                    st.info("No hay órdenes que coincidan con el registro de proveedores y compradores autorizados.")
            
            except Exception as e:
                st.error(f"Error: {e}")
