import streamlit as st
import pandas as pd
import requests
import io
from datetime import datetime

# Configuración de página
st.set_page_config(page_title="Monitor ODC - RIOMARKET", layout="wide")

# --- DATA INICIAL (Calendario) ---
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
        # 1. Identificar día actual
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
            st.info(f"Buscando órdenes para: {', '.join(provs_hoy)}")
            
            # URL RAW DE GITHUB
            url_github = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/%C3%93rdenes%20de%20compra%2016_04_2026.xlsx"
            
            try:
            response = requests.get(url_github)
            if response.status_code == 200:
                excel_data = io.BytesIO(response.content)
                df = pd.read_excel(excel_data, engine='openpyxl')
                df.columns = df.columns.str.strip()
                
                st.markdown("### 📊 Resultado de la Búsqueda")

                for prov in provs_hoy:
                    # Normalizamos el nombre del proveedor para la búsqueda
                    # Usamos escape para que los puntos y paréntesis no rompan el regex
                    prov_limpio = re.escape(prov.strip().upper())
                    
                    # Buscamos coincidencias parciales (ej. que "DIVAR" encuentre "DIVAR C.A.")
                    mask = df['Proveedor'].astype(str).str.upper().str.contains(prov_limpio, na=False, regex=True)
                    resultado = df[mask]
                    
                    if not resultado.empty:
                        campos_web = [
                            'Número de orden', 
                            'Proveedor', 
                            'Estatus', 
                            'Tipo de entrega', 
                            'Tipo de distribución', 
                            'Creado por'
                        ]
                        
                        df_final = resultado[campos_web].rename(columns={'Creado por': 'Comprador'})
                        
                        with st.expander(f"✅ {prov} - {len(df_final)} orden(es) encontrada(s)"):
                            st.table(df_final)
                    else:
                        # Si falla el nombre completo, intentamos buscar solo la primera palabra (ej: "DIVAR")
                        primera_palabra = re.escape(prov.split()[0].upper())
                        mask_fuzzy = df['Proveedor'].astype(str).str.upper().str.contains(primera_palabra, na=False, regex=True)
                        resultado_fuzzy = df[mask_fuzzy]
                        
                        if not resultado_fuzzy.empty:
                            df_final_f = resultado_fuzzy[campos_web].rename(columns={'Creado por': 'Comprador'})
                            with st.expander(f"⚠️ {prov} (Encontrado como coincidencia parcial)"):
                                st.table(df_final_f)
                        else:
                            st.warning(f"⏳ **{prov}**: Orden en proceso / No encontrada")
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
