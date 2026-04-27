import streamlit as st
import pandas as pd
import requests
import io
import sqlite3
from datetime import datetime, timedelta

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Monitor ODC - RIOMARKET", layout="wide")

# --- ESTILOS CSS PARA EL SISTEMA DE COLA (ESTILO TURNO) ---
st.markdown("""
<style>
    .main-order-container {
        background-color: #FFC107;
        color: black;
        border-radius: 15px;
        padding: 30px;
        text-align: center;
        border: 5px solid #E67E22;
        margin-bottom: 20px;
    }
    .main-order-title { font-size: 2rem; font-weight: bold; margin-bottom: 0; }
    .main-order-number { font-size: 8rem; font-weight: 900; line-height: 1; margin: 10px 0; }
    .main-order-info { font-size: 1.5rem; font-weight: bold; }
    
    .queue-card {
        background-color: #f1f1f1;
        color: #333;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 10px;
        border-left: 10px solid #FFC107;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .queue-number { font-size: 2rem; font-weight: bold; color: #E67E22; }
    .queue-details { text-align: right; font-size: 0.9rem; }
</style>
""", unsafe_allow_html=True)

# ... [MANTENER TODAS LAS FUNCIONES DE DB: init_db, registrar_comprador, cargar_semana, etc.] ...

# --- 4. ÁREA PRINCIPAL ---
st.title("📅 Monitor de Órdenes de Compra")

# [MANTENER LÓGICA DE NAVEGACIÓN Y TABLA DE PLANIFICACIÓN]
# ...

st.divider()

# --- 5. LÓGICA DE MONITOREO AUTOMÁTICO (SISTEMA DE COLA) ---
st.subheader("🤖 Monitoreo en Tiempo Real - Sistema de Cola")

dia_hoy_idx = datetime.now().weekday()
dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
dia_hoy_es = dias_semana[dia_hoy_idx]

cal_data = cargar_semana(st.session_state.fecha_referencia) or {d: ["-"] for d in dias_semana}
provs_hoy = cal_data.get(dia_hoy_es, [])

if not provs_hoy or provs_hoy == ["-"]:
    st.info(f"No hay proveedores programados para hoy ({dia_hoy_es}).")
else:
    url_excel = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/ODC_alerta.xlsx"
    
    try:
        # Descarga de datos
        res = requests.get(url_excel)
        df_raw = pd.read_excel(io.BytesIO(res.content), engine='openpyxl')
        
        if not df_raw.empty:
            df_raw.columns = df_raw.columns.str.strip()
            df_raw = df_raw.rename(columns={'Creado por': 'Comprador'})
            df_aut = obtener_compradores_autorizados()
            
            df_aut['key'] = (df_aut['nombre'].str.upper().str.strip() + "|" + 
                             df_aut['comprador_habitual'].str.upper().str.strip())
            set_autorizados = set(df_aut['key'].tolist())

            def validar(row):
                p_ex = str(row['Proveedor']).upper().strip()
                c_ex = str(row['Comprador']).upper().strip()
                if not any(p in p_ex for p in provs_hoy if p != "-"): return False
                return f"{p_ex}|{c_ex}" in set_autorizados

            df_filtrado = df_raw[df_raw.apply(validar, axis=1)].copy()

            if not df_filtrado.empty:
                # --- AQUÍ EMPIEZA LA VISUALIZACIÓN DE COLA ---
                # Ordenar para que la última generada (asumiendo por índice o número) sea la principal
                ordenes = df_filtrado.to_dict('records')
                ultima_orden = ordenes[-1] # La última de la lista
                anteriores = ordenes[:-1][::-1] # El resto, invertidas para ver las más recientes primero

                col_main, col_queue = st.columns([2, 1])

                with col_main:
                    st.markdown(f"""
                        <div class="main-order-container">
                            <div class="main-order-title">ÚLTIMA ORDEN GENERADA</div>
                            <div class="main-order-number">{ultima_orden['Número de orden'][-4:]}</div>
                            <div class="main-order-info">{ultima_orden['Proveedor']}</div>
                            <div style="font-size: 1.2rem;">Comprador: {ultima_orden['Comprador']}</div>
                        </div>
                    """, unsafe_allow_html=True)

                with col_queue:
                    st.markdown("<h4 style='text-align: center;'>ÓRDENES ANTERIORES</h4>", unsafe_allow_html=True)
                    if anteriores:
                        for idx, ord in enumerate(anteriores[:5]): # Mostrar las últimas 5 anteriores
                            st.markdown(f"""
                                <div class="queue-card">
                                    <div class="queue-number">#{ord['Número de orden'][-4:]}</div>
                                    <div class="queue-details">
                                        <b>{ord['Proveedor'][:20]}...</b><br>
                                        {ord['Comprador']}
                                    </div>
                                </div>
                            """, unsafe_allow_html=True)
                    else:
                        st.write("No hay órdenes previas hoy.")
            else:
                st.info(f"✅ Sin órdenes pendientes para {dia_hoy_es} con compradores autorizados.")
    except Exception as e:
        st.error(f"Error al sincronizar datos: {e}")
