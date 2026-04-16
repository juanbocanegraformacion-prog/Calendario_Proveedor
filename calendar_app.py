import streamlit as st
import pandas as pd
import datetime
import requests
import io  # <--- Agrega esta línea para manejar los datos en memoria
from datetime import datetime
import openpyxl
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
    st.subheader("🤖 Ejecución de RPA")
    sucursal_target = st.selectbox("Sucursal a monitorear:", ["CENDI GUATIRE", "CENDI 4 DE MAYO"])
    
    col_btn1, col_btn2 = st.columns(2)
    
    if col_btn1.button("🚀 Iniciar Monitoreo de Hoy", type="primary"):
        # 1. Identificar el día de hoy
        dia_hoy = datetime.now().strftime('%A')
        mapping = {
            "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", 
            "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
        }
        dia_es = mapping.get(dia_hoy)
        
        # 2. Obtener proveedores programados para hoy desde el session_state
        provs_hoy = st.session_state.calendario.get(dia_es, [])
        
        if not provs_hoy:
            st.error(f"No hay proveedores programados para hoy ({dia_es}).")
        else:
            st.info(f"Buscando monitoreo para: {', '.join(provs_hoy)}")
            
            # 3. Descargar el consolidado de GitHub para validar
            url_github = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/Reporte_Alertas_CONSOLIDADO.xlsx"
            
            try:
                response = requests.get(url_github)
                if response.status_code == 200:
                    excel_data = io.BytesIO(response.content)
                    # Leemos el Excel (asegúrate de que la columna se llame 'Proveedor' o ajusta el nombre)
                    df_consolidado = pd.read_excel(excel_data)
                    
                    # Convertimos la columna de proveedores a una lista y normalizamos (limpiar espacios y minúsculas)
                    # Asumimos que la columna se llama 'Proveedor'
                    lista_en_excel = df_consolidado['Proveedor'].astype(str).str.strip().str.upper().tolist()
                    
                    st.markdown("### 📊 Estado de Verificación")
                    
                    # 4. Cruzar datos y mostrar resultados
                    for prov in provs_hoy:
                        prov_normalizado = prov.strip().upper()
                        
                        if prov_normalizado in lista_en_excel:
                            st.success(f"✅ **{prov}**: Aparece en el reporte (Check)")
                        else:
                            st.warning(f"⏳ **{prov}**: Orden en proceso")
                            
                else:
                    st.error(f"No se pudo acceder al reporte en GitHub (Status: {response.status_code})")
            
            except Exception as e:
                st.error(f"Error técnico durante la validación: {e}")

    # --- El segundo botón se mantiene igual para ver el archivo completo ---
    if col_btn2.button("📊 Ver Reporte Consolidado"):
        # (Aquí va tu código anterior de requests e io para mostrar el dataframe completo)
        pass

if __name__ == "__main__":
    main()
