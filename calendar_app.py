import streamlit as st
import pandas as pd
import requests
import io
import json
from datetime import datetime, timedelta, date
import streamlit.components.v1 as components
from supabase import create_client, Client

# ------------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA
# ------------------------------------------------------------
st.set_page_config(page_title="Monitor ODC - RIOMARKET", layout="wide")

# ------------------------------------------------------------
# CSS PERSONALIZADO (carrusel)
# ------------------------------------------------------------
st.markdown("""
<style>
    .carousel-card {
        background-color: #FFFFFF;
        border: 5px solid #2E7D32;
        border-radius: 20px;
        box-shadow: 0 8px 16px rgba(0,0,0,0.25), 0 12px 40px rgba(0,0,0,0.15);
        padding: 5vw;
        text-align: center;
        margin: 20px auto;
        width: 90%;
        max-width: 800px;
    }
    .carousel-title {
        font-size: clamp(2rem, 5vw, 3rem);
        font-weight: bold;
        color: #2E7D32;
        margin-bottom: 15px;
    }
    .carousel-order-number {
        font-size: clamp(3rem, 15vw, 8rem);
        font-weight: 900;
        color: #1B5E20;
        line-height: 1;
    }
    .carousel-info {
        font-size: clamp(1.5rem, 5vw, 2.5rem);
        font-weight: bold;
        color: #333;
    }
    .carousel-detail {
        font-size: clamp(1.2rem, 4vw, 2rem);
        font-weight: bold;
        color: #333;
        margin-top: 10px;
    }
    @media (max-width: 768px) {
        .carousel-card {
            padding: 20px;
            width: 98%;
            border-width: 3px;
            border-radius: 15px;
        }
        .carousel-order-number {
            font-size: 3.5rem;
        }
        .carousel-title {
            font-size: 1.5rem;
        }
        .carousel-info {
            font-size: 1.3rem;
        }
        .carousel-detail {
            font-size: 1.1rem;
        }
    }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------
# CONFIGURACIÓN DE SUPABASE
# ------------------------------------------------------------
# Secrets esperados en Streamlit Cloud:
# supabase_url = "https://xxxxxxxxxxxx.supabase.co"
# supabase_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."  (anon key)

supabase: Client = create_client(
    st.secrets["supabase_url"],
    st.secrets["supabase_key"]
)

# ------------------------------------------------------------
# VARIABLES GLOBALES
# ------------------------------------------------------------
dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

# ------------------------------------------------------------
# FUNCIONES DE DATOS (SUPABASE)
# ------------------------------------------------------------
def cargar_semana(fecha_consulta):
    """Carga la planificación de la semana indicada. Si no existe, busca la semana anterior más reciente."""
    fecha_str = fecha_consulta.isoformat()  # 'YYYY-MM-DD'
    
    resp = supabase.table("calendario_historico") \
        .select("dia_semana, proveedores") \
        .eq("fecha_semana", fecha_str) \
        .execute()
    
    if resp.data:
        result = {d: [] for d in dias_semana}
        for row in resp.data:
            dia = row["dia_semana"]
            provs = row["proveedores"] if row["proveedores"] else []
            if dia in result:
                result[dia] = provs
        return result
    
    # Buscar la semana anterior más reciente
    resp_ant = supabase.table("calendario_historico") \
        .select("fecha_semana, dia_semana, proveedores") \
        .lt("fecha_semana", fecha_str) \
        .order("fecha_semana", desc=True) \
        .limit(7) \
        .execute()
    
    if resp_ant.data:
        ultima_fecha = resp_ant.data[0]["fecha_semana"]
        result = {d: [] for d in dias_semana}
        for row in resp_ant.data:
            if row["fecha_semana"] == ultima_fecha:
                dia = row["dia_semana"]
                provs = row["proveedores"] if row["proveedores"] else []
                if dia in result:
                    result[dia] = provs
        return result
    
    return {d: [] for d in dias_semana}

def guardar_calendario(fecha, calendario_dict):
    """Guarda la planificación de una semana completa en Supabase."""
    fecha_str = fecha.isoformat()
    # Eliminar registros previos de esa semana
    supabase.table("calendario_historico").delete().eq("fecha_semana", fecha_str).execute()
    
    rows = []
    for dia, lista_provs in calendario_dict.items():
        provs_limpios = [p.strip().upper() for p in lista_provs if p.strip()]
        rows.append({
            "fecha_semana": fecha_str,
            "dia_semana": dia,
            "proveedores": provs_limpios
        })
    
    if rows:
        supabase.table("calendario_historico").insert(rows).execute()

def registrar_comprador(proveedor, comprador):
    """Inserta un nuevo par proveedor-comprador. Retorna True si se creó, False si ya existe."""
    p_up = proveedor.strip().upper()
    c_up = comprador.strip().upper()
    
    resp = supabase.table("proveedores_maestro") \
        .select("id") \
        .eq("nombre", p_up) \
        .eq("comprador_habitual", c_up) \
        .execute()
    
    if resp.data:
        return False
    
    supabase.table("proveedores_maestro") \
        .insert({"nombre": p_up, "comprador_habitual": c_up}) \
        .execute()
    return True

def eliminar_comprador(id_registro):
    """Elimina un registro de proveedor_maestro por su id."""
    supabase.table("proveedores_maestro").delete().eq("id", id_registro).execute()

def obtener_compradores_autorizados():
    """Devuelve un DataFrame con id, nombre, comprador_habitual."""
    resp = supabase.table("proveedores_maestro") \
        .select("id, nombre, comprador_habitual") \
        .order("nombre") \
        .execute()
    
    if resp.data:
        return pd.DataFrame(resp.data)
    else:
        return pd.DataFrame(columns=["id", "nombre", "comprador_habitual"])

def obtener_proveedores_registrados():
    """Lista de nombres únicos de proveedores."""
    resp = supabase.table("proveedores_maestro") \
        .select("nombre") \
        .execute()
    
    if resp.data:
        nombres = sorted(list(set(row["nombre"] for row in resp.data)))
        return nombres
    return []

# ------------------------------------------------------------
# AUTENTICACIÓN POR CONTRASEÑA
# ------------------------------------------------------------
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.title("Inicio de sesión requerido")
    with st.form("login_form"):
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Acceder")
        if submitted:
            if password == "RioMarket2026":  # Cambia la contraseña aquí
                st.session_state.autenticado = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta")
    st.stop()

# ------------------------------------------------------------
# GESTIÓN DE FECHAS
# ------------------------------------------------------------
if 'fecha_referencia' not in st.session_state:
    hoy = datetime.now()
    st.session_state.fecha_referencia = (hoy - timedelta(days=hoy.weekday())).date()

# ------------------------------------------------------------
# SIDEBAR
# ------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Panel de Configuración")

    with st.expander("📅 Planificación Semanal", expanded=True):
        dia_edit = st.selectbox("Día a editar:", dias_semana)
        cal_actual = cargar_semana(st.session_state.fecha_referencia)
        provs_registrados = obtener_proveedores_registrados()
        if not provs_registrados:
            st.warning("No hay proveedores registrados aún. Agregue al menos uno en la sección 'Registro Compradores' primero.")
        else:
            seleccion_actual = [p for p in cal_actual.get(dia_edit, []) if p in provs_registrados]
            nuevos_seleccionados = st.multiselect(
                "Proveedores para este día:",
                options=provs_registrados,
                default=seleccion_actual
            )
            if st.button("💾 Guardar planificación"):
                cal_actual[dia_edit] = [p.strip().upper() for p in nuevos_seleccionados]
                guardar_calendario(st.session_state.fecha_referencia, cal_actual)
                st.success("Planificación actualizada.")
                st.rerun()

    with st.expander("👤 Registro Compradores"):
        st.caption("Agregar proveedor y comprador")
        new_p = st.text_input("Proveedor:", key="np")
        new_c = st.text_input("Comprador asignado:", key="nc")
        if st.button("➕ Registrar nuevo par"):
            if new_p and new_c:
                if registrar_comprador(new_p, new_c):
                    st.success(f"Registrado: {new_p.upper()} → {new_c.upper()}")
                else:
                    st.warning("Ese Registro ya existe.")
                st.rerun()
            else:
                st.error("Complete ambos campos.")
        st.divider()
        st.caption("Gestión de registros existentes")
        df_m = obtener_compradores_autorizados()
        if not df_m.empty:
            edited_m = st.data_editor(
                df_m,
                column_config={"id": None},
                hide_index=True,
                use_container_width=True,
                key="editor_compradores"
            )
            if st.button("🔄 Aplicar cambios"):
                for _, row in edited_m.iterrows():
                    supabase.table("proveedores_maestro") \
                        .update({
                            "nombre": row['nombre'].upper(),
                            "comprador_habitual": row['comprador_habitual'].upper()
                        }) \
                        .eq("id", row['id']) \
                        .execute()
                st.success("Registros actualizados.")
                st.rerun()

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

# ------------------------------------------------------------
# ÁREA PRINCIPAL
# ------------------------------------------------------------
st.title("📅 Monitor de Órdenes de Compra")

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
columnas_ordenadas = [dia for dia in dias_semana if dia in df_visual.columns]
df_visual = df_visual[columnas_ordenadas]
st.dataframe(df_visual, use_container_width=True, hide_index=True)

# ------------------------------------------------------------
# 🔧 SECCIÓN DE VERIFICACIÓN DE DATOS (DEBUG)
# ------------------------------------------------------------
with st.expander("🔧 Verificar datos en Supabase (solo para administrador)"):
    st.subheader("Tabla `proveedores_maestro`")
    df_prov = obtener_compradores_autorizados()
    if not df_prov.empty:
        st.dataframe(df_prov)
    else:
        st.info("No hay registros en proveedores_maestro.")

    st.subheader("Últimas semanas en `calendario_historico`")
    # Obtener hasta 5 semanas recientes
    resp_semanas = supabase.table("calendario_historico") \
        .select("fecha_semana, dia_semana, proveedores") \
        .order("fecha_semana", desc=True) \
        .limit(35) \  # 5 semanas * 7 días = 35, aseguramos todas
        .execute()

    if resp_semanas.data:
        df_hist = pd.DataFrame(resp_semanas.data)
        # Agrupar un poco para mostrar la semana actual destacada
        st.dataframe(df_hist)
        # Mostrar también cuál es la semana actual que estamos visualizando
        st.caption(f"Semana activa en pantalla: {st.session_state.fecha_referencia.strftime('%Y-%m-%d')}")
    else:
        st.info("No hay datos en calendario_historico.")
        
st.divider()

# ------------------------------------------------------------
# SISTEMA CARRUSEL (rotación automática cada 6 segundos)
# ------------------------------------------------------------
st.subheader("🤖 Monitoreo en Tiempo Real")

dia_hoy_es = dias_semana[datetime.now().weekday()]
provs_hoy = cal_data.get(dia_hoy_es, [])

if not provs_hoy:
    st.info(f"Hoy ({dia_hoy_es}) no hay proveedores planificados.")
else:
    url = "https://raw.githubusercontent.com/juanbocanegraformacion-prog/Calendario_Proveedor/main/ODC_alerta.xlsx"
    try:
        res = requests.get(url)
        df_raw = pd.read_excel(io.BytesIO(res.content))
        df_raw.columns = df_raw.columns.str.strip()
        df_raw = df_raw.rename(columns={
            'Creado por': 'Comprador',
            'Sucursal destino': 'SucursalDestino'
        })

        df_aut = obtener_compradores_autorizados()
        if df_aut.empty:
            st.warning("No hay pares Proveedor-Comprador registrados. Agréguelos en el panel lateral.")
        else:
            df_aut['key'] = (
                df_aut['nombre'].str.upper().str.strip() + "|" +
                df_aut['comprador_habitual'].str.upper().str.strip()
            )
            set_aut = set(df_aut['key'].tolist())
            proveedores_upper = [p.strip().upper() for p in provs_hoy]

            def validar(row):
                p = str(row['Proveedor']).upper().strip()
                c = str(row['Comprador']).upper().strip()
                if p not in proveedores_upper:
                    return False
                return f"{p}|{c}" in set_aut

            df_f = df_raw[df_raw.apply(validar, axis=1)].copy()

            if not df_f.empty:
                ordenes = []
                for _, row in df_f.iterrows():
                    ordenes.append({
                        'numero': str(row['Número de orden'])[-19:],
                        'proveedor': row['Proveedor'],
                        'comprador': row['Comprador'],
                        'sucursal': row['SucursalDestino']
                    })
                ordenes_json = json.dumps(ordenes)

                carrusel_html = f"""
                <style>
                .carousel-card {{
                    background-color: #FFFFFF;
                    border: 5px solid #2E7D32;
                    border-radius: 20px;
                    box-shadow: 0 8px 16px rgba(0,0,0,0.25), 0 12px 40px rgba(0,0,0,0.15);
                    padding: 5vw;
                    text-align: center;
                    margin: 20px auto;
                    width: 90%;
                    max-width: 800px;
                }}
                .carousel-title {{
                    font-size: clamp(2rem, 5vw, 3rem);
                    font-weight: bold;
                    color: #2E7D32;
                    margin-bottom: 15px;
                }}
                .carousel-order-number {{
                    font-size: clamp(3rem, 15vw, 8rem);
                    font-weight: 900;
                    color: #1B5E20;
                    line-height: 1;
                }}
                .carousel-info {{
                    font-size: clamp(1.5rem, 5vw, 2.5rem);
                    font-weight: bold;
                    color: #333;
                }}
                .carousel-detail {{
                    font-size: clamp(1.2rem, 4vw, 2rem);
                    font-weight: bold;
                    color: #333;
                    margin-top: 10px;
                }}
                @media (max-width: 768px) {{
                    .carousel-card {{
                        padding: 20px;
                        width: 98%;
                        border-width: 3px;
                        border-radius: 15px;
                    }}
                    .carousel-order-number {{
                        font-size: 3.5rem;
                    }}
                    .carousel-title {{
                        font-size: 1.5rem;
                    }}
                    .carousel-info {{
                        font-size: 1.3rem;
                    }}
                    .carousel-detail {{
                        font-size: 1.1rem;
                    }}
                }}
                </style>
                <div id="carousel-container">
                    <div class="carousel-card">
                        <div class="carousel-title">ORDEN DE COMPRA</div>
                        <div class="carousel-order-number">#---</div>
                        <div class="carousel-info">---</div>
                        <div class="carousel-detail">Comprador: ---</div>
                        <div class="carousel-detail">Sucursal Destino: ---</div>
                    </div>
                </div>
                <script>
                const orders = {ordenes_json};
                let currentIndex = 0;
                function showOrder(index) {{
                    const order = orders[index];
                    document.querySelector('#carousel-container .carousel-order-number').textContent = '#' + order.numero;
                    document.querySelector('#carousel-container .carousel-info').textContent = order.proveedor;
                    const details = document.querySelectorAll('#carousel-container .carousel-detail');
                    details[0].textContent = 'Comprador: ' + order.comprador;
                    details[1].textContent = 'Sucursal Destino: ' + order.sucursal;
                }}
                showOrder(0);
                setInterval(() => {{
                    currentIndex = (currentIndex + 1) % orders.length;
                    showOrder(currentIndex);
                }}, 6000);
                </script>
                """
                components.html(carrusel_html, height=550)
                st.caption(f"🔄 {len(ordenes)} órdenes validadas rotando cada 6 segundos")
            else:
                st.info("Buscando órdenes validadas... (ninguna coincide aún)")
                with st.expander("🔍 Ver diagnóstico de filtros"):
                    st.write("**Proveedores planificados para hoy:**", proveedores_upper)
                    st.write("**Pares Proveedor-Comprador registrados:**")
                    st.dataframe(df_aut[['nombre', 'comprador_habitual']].rename(
                        columns={'nombre': 'Proveedor', 'comprador_habitual': 'Comprador'}
                    ))
                    st.caption("Asegúrese de que el nombre del proveedor en la planificación sea **exactamente igual** al que aparece en el archivo Excel (respetando comas, puntos, espacios).")
    except Exception as e:
        st.error(f"Error en la sincronización: {e}")
