import streamlit as st
import pandas as pd
import requests
import io
from datetime import datetime

# Configuración de página
st.set_page_config(page_title="Monitor ODC - RIOMARKET", layout="wide")

# --- DATA INICIAL ---
if 'calendario' not in st.session_state:
    st.session_state.calendario = {
        "Lunes": ["Polar", "Dimassi", "Ponce"],
        "Martes": ["Colgate", "Isola/Bonbon", "Jai - Suro"],
        "Miércoles": ["Alive", "Fisa-Wayne"],
        "Jueves": ["Pharsana", "American Colors", "Medifort"],
        "Viernes": ["Oxford", "Joneal"],
        "Sábado": [],
        "Domingo": []
    }

def main():
    st.title("📅 Gestión de Calendario de Proveedores")
    st.markdown("### Configuración de Monitoreo Semanal")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Vista de Planificación")
        df_cal = pd.DataFrame.from_dict(st.session_state.calendario, orient='index').transpose()
        st.dataframe(df_cal.fillna("-"), use_container_width=True)
        st.info("💡 El bot verificará los proveedores según el día actual del servidor.")

    with col2:
        st.subheader("⚙️ Panel de Control")
        dia_editar = st.selectbox("Seleccionar día para editar:", list(st.session_state.calendario.keys()))
        proveedores_actuales = ", ".join(st.session_state.calendario[dia_editar])
        nuevos_provs = st.text_area(f"Proveedores para {dia_editar}:", value=proveedores_actuales)
        
        if st.button("Guardar Cambios"):
            st.session_state.calendario[dia_editar] = [p.strip() for p in nuevos_provs.split(",") if p.strip()]
            st.success(f"Calendario de {dia_editar} actualizado.")
            st.rerun()

    st.divider()
    st.subheader("🤖 Ejecución de RPA")
    sucursal_target = st.selectbox("Sucursal a monitorear:", ["CENDI GUATIRE", "CENDI 4 DE MAYO"])
    
    col_btn1, col_btn2 = st.columns(2)
    
    if col_btn1.button("🚀 Iniciar Monitoreo de Hoy", type="primary"):
        dia_hoy = datetime.now().strftime('%A')
        mapping = {
            "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", 
            "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
        }
        dia_es = mapping.get(dia_hoy)
        provs_hoy = st.session_state.calendario.get(dia_es, [])
        
        if not provs_hoy:
            st.error(f"No hay proveedores programados para hoy ({dia_es}).")
        else:
            st.info(f"Buscando monitoreo para: {', '.join(provs_hoy)}")
            
            # URL RAW DE GITHUB (Corregida para descarga directa)
            url_github = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/%C3%93rdenes%20de%20compra%2016_04_2026.xlsx"
            
            try:
                response = requests.get(url_github)
                if response.status_code == 200:
                    excel_data = io.BytesIO(response.content)
                    # Especificamos engine='openpyxl' para evitar el error de formato
                    df = pd.read_excel(excel_data, engine='openpyxl')
                    
                    # Normalización de la columna C (Proveedor)
                    # Columna C es índice 2, Columna A es índice 0, etc.
                    df.columns = df.columns.str.strip() 
                    
                    st.markdown("### 📊 Resultado de la Búsqueda")
                    
                    for prov in provs_hoy:
                        prov_buscado = prov.strip().upper()
                        # Filtrar filas donde el proveedor coincida (Columna 'Proveedor')
                        filtro = df[df['Proveedor'].astype(str).str.upper().str.contains(prov_buscado, na=False)]
                        
                        if not filtro.empty:
                            for index, row in filtro.iterrows():
                                with st.expander(f"✅ {prov} - Orden: {row['Número de orden']}"):
                                    st.write(f"**Estatus:** {row['Estatus']}")
                                    st.write(f"**Tipo de entrega:** {row['Tipo de entrega']}")
                                    st.write(f"**Distribución:** {row['Tipo de distribución']}")
                                    st.write(f"**Comprador:** {row['Creado por']}") # Ajustado según el archivo adjunto (Creado por)
                        else:
                            st.warning(f"⏳ **{prov}**: Orden en proceso / No encontrada")
                else:
                    st.error(f"Error al descargar de GitHub. Status: {response.status_code}")
            except Exception as e:
                st.error(f"Error técnico durante la validación: {e}")

    if col_btn2.button("📊 Ver Reporte Consolidado"):
        url_github = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/%C3%93rdenes%20de%20compra%2016_04_2026.xlsx"
        response = requests.get(url_github)
        if response.status_code == 200:
            df_full = pd.read_excel(io.BytesIO(response.content), engine='openpyxl')
            st.dataframe(df_full)

if __name__ == "__main__":
    main()
