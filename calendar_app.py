import streamlit as st
import pandas as pd
import requests
import io
from datetime import datetime

# Configuración de página
st.set_page_config(page_title="Monitor ODC - RIOMARKET", layout="wide")

# --- ESTILOS CSS PARA REPLICAR EL DISEÑO ---
st.markdown("""
    <style>
    .week-card {
        border: 1px solid #ddd;
        border-radius: 10px;
        padding: 15px;
        text-align: center;
        background-color: #f9f9f9;
        margin-bottom: 10px;
    }
    .week-card-alert {
        border: 1px solid #ffcc00;
        background-color: #fff9e6;
    }
    .rpa-card {
        border: 1px solid #e0e0e0;
        border-radius: 5px;
        padding: 10px;
        margin-bottom: 5px;
        background-color: #ffffff;
    }
    .rpa-header {
        display: flex;
        justify-content: space-between;
        font-weight: bold;
        background-color: #f1f3f9;
        padding: 8px;
        border-radius: 5px;
    }
    .order-line {
        font-size: 0.9em;
        border-bottom: 1px solid #f0f0f0;
        padding: 5px 0;
        color: #333;
    }
    .sidebar-content {
        padding: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- BASE DE DATOS Y ESTADO INICIAL ---
if 'db_compradores' not in st.session_state:
    st.session_state.db_compradores = {
        "DIVAR": "Marvel García",
        "OXFORD": "Maikel García",
        "JONEAL": "Maikel García",
        "POLAR": "Jesús Pérez",
        "COLGATE": "Verónica Lugo"
    }

if 'historial' not in st.session_state:
    st.session_state.historial = {
        "Semana 10": {"status": "✅ Completo", "count": "12 proveedores", "color": "normal"},
        "Semana 11": {"status": "⚠️ Pendiente de revisión", "count": "1 error, 15 proveedores", "color": "alert"},
        "Semana 12": {"status": "⚠ No monitoreado", "count": "0 proveedores", "color": "normal"},
        "Semana Actual": {"status": "✅ Completo", "count": "14 proveedores", "color": "normal"}
    }

if 'calendario' not in st.session_state:
    st.session_state.calendario = {
        "Lunes": ["Polar", "Dimassi", "Ponce"],
        "Martes": ["Colgate", "Isola/Bonbon", "Jai - Suro"],
        "Miércoles": ["Alive", "Fisa-Wayne"],
        "Jueves": ["Pharsana", "American Colors", "Medifort"],
        "Viernes": ["Oxford", "Joneal", "DIVAR"],
        "Sábado": [],
        "Domingo": []
    }

if 'selected_week' not in st.session_state:
    st.session_state.selected_week = "Semana Actual"

# --- SIDEBAR: MENÚ DE CONFIGURACIÓN ---
with st.sidebar:
    st.header("⚙️ Menú de Configuración")
    dia_editar = st.selectbox("Seleccionar día para editar:", list(st.session_state.calendario.keys()), index=4)
    
    nuevo_prov = st.text_input(
        "Añadir proveedor para monitoreo:", 
        placeholder="Añadir proveedor para monitoreo (Ej: DIVAR, Oxford...)"
    )
    
    if st.button("Guardar Cambios", use_container_width=True):
        if nuevo_prov:
            st.session_state.calendario[dia_editar].append(nuevo_prov.strip())
            st.success(f"Proveedor {nuevo_prov} añadido a {dia_editar}")
            st.rerun()

# --- CUERPO PRINCIPAL ---
st.title("📅 Gestión de Calendario de Proveedores")
st.subheader("Vista de Planificación")

# Seccion de Historial Semanal
st.write("### Semanas Anteriores")
cols_hist = st.columns(4)
for i, (semana, info) in enumerate(st.session_state.historial.items()):
    with cols_hist[i]:
        card_class = "week-card-alert" if info['color'] == "alert" else ""
        if st.button(f"{semana}\n\n{info['status']}\n{info['count']}", key=f"btn_{semana}", use_container_width=True):
            st.session_state.selected_week = semana

# Tabla de Planificación
df_cal = pd.DataFrame.from_dict(st.session_state.calendario, orient='index').transpose()
st.dataframe(df_cal.fillna("-"), use_container_width=True)

st.divider()

# Sección de Ejecución RPA e Informe Lateral
main_col, drawer_col = st.columns([3, 1])

with main_col:
    st.subheader("🤖 Ejecución de RPA")
    sucursal_target = st.selectbox("Sucursal a monitorear:", ["CENDIGLATIRE", "CENDI 4 DE MAYO"])
    
    if st.button("🚀 Iniciar Monitoreos de Hoy", type="primary"):
        # Lógica de simulación de búsqueda basada en el script original
        st.write("### Resultados de RPA")
        
        # Simulamos carga de datos para los proveedores de hoy (Viernes en el ejemplo)
        provs_hoy = st.session_state.calendario["Viernes"]
        
        for prov in provs_hoy:
            nombre_prov = prov.strip().upper()
            comprador = st.session_state.db_compradores.get(nombre_prov, "Asignado")
            
            # Formato de tarjeta fija según imagen
            st.markdown(f"""
                <div class="rpa-card">
                    <div class="rpa-header">
                        <span>{nombre_prov}, 3 órdenes encontradas - Última ejecución: 10:32 AM</span>
                        <span>👁️</span>
                    </div>
                    <div class="order-line">ID OC-01-023-00011833 | Total Delivery / Distribuida | Comprador: {comprador}</div>
                    <div class="order-line">ID OC-01-023-00011853 | Total Delivery / Distribuida | Comprador: {comprador}</div>
                    <div class="order-line">ID OC-01-023-00011853 | Total Delivery / Distribuida | Comprador: {comprador}</div>
                </div>
            """, unsafe_allow_html=True)
            
    st.button("📊 Ver Reporte Completo")

with drawer_col:
    # Simulación de Drawer Lateral con JSON
    st.markdown("#### leporte Completo de DIVAR")
    report_json = {
        "ID": "DIVAR",
        "semanas_monitoreo": 708,
        "proveedores": {
            "Tipo Delivery": "Total",
            "Estatus": "Autorizada",
            "Tipo de distribución": "Distribuida"
        },
        "Remoto": "alere"
    }
    st.json(report_json)

if __name__ == "__main__":
    pass
