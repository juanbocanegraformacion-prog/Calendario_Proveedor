import streamlit as st
import pandas as pd
from datetime import datetime
import calendar

# Configuración de página
st.set_page_config(page_title="Monitor ODC - RIOMARKET", layout="wide")

# --- DATA INICIAL (Basada en tu imagen de Abril 2026) ---
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
        # Convertimos el diccionario a un DataFrame para visualizarlo como tabla
        df_cal = pd.DataFrame.from_dict(st.session_state.calendario, orient='index').transpose()
        st.dataframe(df_cal.fillna("-"), use_container_width=True)

        # Simulación del calendario de Abril (Días específicos)
        st.info("💡 El bot verificará los proveedores según el día actual del servidor.")

    with col2:
        st.subheader("⚙️ Panel de Control")
        dia_editar = st.selectbox("Seleccionar día para editar:", list(st.session_state.calendario.keys()))
        
        # Gestionar proveedores por día
        proveedores_actuales = ", ".join(st.session_state.calendario[dia_editar])
        nuevos_provs = st.text_area(f"Proveedores para {dia_editar}:", value=proveedores_actuales)
        
        if st.button("Guardar Cambios"):
            st.session_state.calendario[dia_editar] = [p.strip() for p in nuevos_provs.split(",") if p.strip()]
            st.success(f"Calendario de {dia_editar} actualizado.")
            st.rerun()

    st.divider()

    # --- SECCIÓN DE EJECUCIÓN DEL BOT ---
    st.subheader("🤖 Ejecución de RPA")
    sucursal_target = st.selectbox("Sucursal a monitorear:", ["CENDI GUATIRE", "CENDI 4 DE MAYO"])
    
    col_btn1, col_btn2 = st.columns(2)
    
    if col_btn1.button("🚀 Iniciar Monitoreo de Hoy", type="primary"):
        # Aquí es donde integrarías tu script de Selenium
        dia_hoy = datetime.now().strftime('%A') # Obtener día en inglés o mapear a español
        # Mapeo simple para el ejemplo
        mapping = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", 
                   "Thursday": "Jueves", "Friday": "Viernes"}
        dia_es = mapping.get(dia_hoy, "Sábado")
        
        provs_hoy = st.session_state.calendario.get(dia_es, [])
        
        if provs_hoy:
            st.warning(f"Ejecutando Selenium para: {', '.join(provs_hoy)} en {sucursal_target}...")
            # Aquí llamarías a tu función main() del script de Selenium
            # procesar_sucursal_y_acumular(driver, sucursal_target, ...)
        else:
            st.error("No hay proveedores programados para hoy.")

    if col_btn2.button("📊 Ver Reporte Consolidado"):
        # URL Raw del archivo en GitHub
        url_github = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/Reporte_Alertas_CONSOLIDADO.xlsx"
        
        try:
            # 1. Descargamos el archivo de GitHub
            response = requests.get(url_github)
            
            if response.status_code == 200:
                # 2. Cargamos el contenido en Pandas usando un buffer de memoria
                excel_data = io.BytesIO(response.content)
                df_reporte = pd.read_excel(excel_data)
                
                st.success("✅ Reporte cargado desde GitHub con éxito.")
                
                # 3. Mostramos los datos directamente en la Web
                st.subheader("Vista Previa del Reporte")
                st.dataframe(df_reporte, use_container_width=True)
                
                # 4. Botón opcional para descargar localmente
                st.download_button(
                    label="📥 Descargar este Excel",
                    data=response.content,
                    file_name="Reporte_Alertas_CONSOLIDADO.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error(f"❌ No se pudo acceder al archivo. Status: {response.status_code}")
                
        except Exception as e:
            st.error(f"⚠️ Ocurrió un error al conectar con GitHub: {e}")

if __name__ == "__main__":
    main()
