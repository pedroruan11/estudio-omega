import streamlit as st
import datetime
import pandas as pd
import urllib.parse
import os
from streamlit_calendar import calendar

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gestão de Ensaio - Estúdio Ómega", page_icon="🎸", layout="wide")

# --- DESIGN SYSTEM: TEMA ESCURO PROFISSIONAL & ALTO CONTRASTE ---
st.markdown("""
<style>
    /* Importando fonte profissional (Inter) */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    /* Cores Globais e Tipografia Geral */
    .stApp {
        background-color: #000000;
        color: #ffffff;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    
    /* Garantir que textos comuns, labels e parágrafos fiquem bem brancos/legíveis */
    p, span, label, div, .stMarkdown, .stText {
        color: #f1f1f1 !important;
        font-family: 'Inter', sans-serif;
    }
    
    /* Barra Lateral (Sidebar) */
    [data-testid="stSidebar"] {
        background-color: #0c0c0c;
        border-right: 1px solid #1f1f1f;
    }
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] label {
        color: #e0e0e0 !important;
    }
    
    /* Esconde as bolinhas (radio buttons) nativas do menu lateral */
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label div:first-child {
        display: none !important;
    }
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
        background-color: transparent;
        padding: 8px 12px;
        border-radius: 6px;
        transition: background 0.2s;
        margin-bottom: 4px;
    }
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:hover {
        background-color: #1a1a1a;
        cursor: pointer;
    }
    
    /* Títulos e Cabeçalhos com destaque elegante */
    h1, h2, h3, h4, h5, h6 {
        color: #f39c12 !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 700 !important;
    }
    
    /* Botões Principais */
    .stButton>button {
        background-color: #f39c12;
        color: #000000;
        border: none;
        border-radius: 6px;
        font-weight: 600;
        font-family: 'Inter', sans-serif;
        padding: 0.5rem 1rem;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background-color: #d68910;
        color: #ffffff;
        box-shadow: 0 4px 14px rgba(243, 156, 18, 0.4);
    }
    
    /* Inputs, Selectbox e Campos de Texto altamente legíveis */
    .stTextInput>div>div>input, .stSelectbox>div>div>select, .stDateInput>div>div>input, .stTimeInput>div>div>input {
        background-color: #121212 !important;
        color: #ffffff !important;
        border: 1px solid #333333 !important;
        border-radius: 6px !important;
        font-family: 'Inter', sans-serif !important;
    }
    .stTextInput>div>div>input:focus, .stSelectbox>div>div>select:focus {
        border-color: #f39c12 !important;
        box-shadow: 0 0 6px rgba(243, 156, 18, 0.5) !important;
    }
    
    /* Correção total do Dropdown/Popover (Selectbox e DateInput nativos do Streamlit) para tema escuro */
    div[data-baseweb="popover"], div[data-baseweb="menu"], div[data-baseweb="calendar"] {
        background-color: #141414 !important;
        color: #ffffff !important;
        border: 1px solid #333333 !important;
        border-radius: 6px !important;
    }
    
    /* Itens de listas suspensas (Selectbox dropdown options) */
    div[data-baseweb="menu"] ul, div[data-baseweb="menu"] li {
        background-color: #141414 !important;
        color: #ffffff !important;
    }
    div[data-baseweb="menu"] li:hover {
        background-color: #222222 !important;
        color: #f39c12 !important;
    }

    /* Estilização do Mini Calendário (Date Picker Popup) */
    div[data-baseweb="calendar"] header, div[data-baseweb="calendar"] div {
        background-color: #141414 !important;
        color: #ffffff !important;
    }
    div[data-baseweb="calendar"] button {
        color: #ffffff !important;
    }
    div[data-baseweb="calendar"] button:hover {
        background-color: #222222 !important;
        color: #f39c12 !important;
    }

    /* Textos placeholder dos inputs */
    input::placeholder {
        color: #888888 !important;
        opacity: 1;
    }

    /* Cards de Informação e Alertas */
    .stAlert {
        background-color: #121212;
        border: 1px solid #262626;
        color: #ffffff !important;
        border-radius: 6px;
    }
    
    /* Métricas */
    [data-testid="stMetricValue"] {
        color: #f39c12 !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 700 !important;
    }
    [data-testid="stMetricLabel"] {
        color: #bbbbbb !important;
        font-family: 'Inter', sans-serif !important;
    }
    
    /* Tabelas e Dataframes */
    [data-testid="stDataFrame"] {
        border: 1px solid #222222;
        border-radius: 6px;
    }

    /* --- TEMA ESCURO ROBUSTO PARA O CALENDÁRIO VISUAL (FullCalendar) --- */
    .fc {
        background-color: #0d0d0d !important;
        color: #ffffff !important;
        border-radius: 8px;
        padding: 10px;
    }
    .fc-theme-standard td, .fc-theme-standard th, .fc-theme-standard .fc-scrollgrid {
        border-color: #262626 !important;
        background-color: #0d0d0d !important;
    }
    .fc-daygrid-day {
        background-color: #121212 !important;
    }
    .fc-daygrid-day:hover {
        background-color: #1a1a1a !important;
    }
    .fc-col-header-cell {
        background-color: #161616 !important;
    }
    .fc-col-header-cell-cushion, .fc-daygrid-day-number {
        color: #ffffff !important;
        font-weight: 600;
    }
    /* Dias de outros meses que aparecem no grid */
    .fc-day-other .fc-daygrid-day-number {
        color: #555555 !important;
    }
    .fc-day-today {
        background-color: #1f1b11 !important;
    }
    .fc-toolbar {
        background-color: #121212 !important;
        padding: 10px;
        border-radius: 6px;
    }
    .fc-toolbar-title {
        color: #f39c12 !important;
        font-size: 1.2rem !important;
        font-weight: 600 !important;
    }
    .fc-button {
        background-color: #1f1f1f !important;
        border: 1px solid #333333 !important;
        color: #ffffff !important;
        font-weight: 600 !important;
    }
    .fc-button:hover {
        background-color: #f39c12 !important;
        color: #000000 !important;
        border-color: #f39c12 !important;
    }
    .fc-button-active {
        background-color: #f39c12 !important;
        color: #000000 !important;
    }
    .fc-event-title {
        font-size: 11px !important;
        font-weight: 500 !important;
        white-space: normal !important;
    }
    .fc-event {
        padding: 3px 6px !important;
        margin-bottom: 2px !important;
        background-color: #1a1a1a !important;
        border-left: 3px solid #f39c12 !important;
        border-right: none !important;
        border-top: none !important;
        border-bottom: none !important;
        color: #ffffff !important;
    }
</style>
""", unsafe_allow_html=True)

# ID da Planilha do Google Sheets
SHEET_ID = "1Cpz09lM3tPnx1kG2pk4UAKR3bgIQ8WPmMJnRP6EpLEY"

# --- CARREGAR DADOS DA PLANILHA ---
@st.cache_data(ttl=5)
def carregar_dados_aba(nome_aba):
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={nome_aba}"
    try:
        df = pd.read_csv(url, dtype=str)
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        return pd.DataFrame()

# --- LOGIN DOS SÓCIOS ---
def login():
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<div style='margin-top: 5vh;'></div>", unsafe_allow_html=True)
        
        with st.container():
            if os.path.exists("logo.png"):
                col_img1, col_img2, col_img3 = st.columns([1, 1.5, 1])
                with col_img2:
                    st.image("logo.png", width=140)
            else:
                st.markdown("<h2 style='text-align: center; color: #f39c12; margin-bottom: 0px;'>⚡ ESTÚDIO ÓMEGA</h2>", unsafe_allow_html=True)
                
            st.markdown("<p style='text-align: center; color: #cccccc; font-size: 0.95rem; margin-bottom: 25px;'>Painel de Gestão Restrito</p>", unsafe_allow_html=True)
            
            username = st.text_input("Usuário", placeholder="Digite seu usuário")
            password = st.text_input("Senha", type="password", placeholder="••••••••")
            
            st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
            
            if st.button("Entrar no Sistema", use_container_width=True):
                df_users = carregar_dados_aba("Administradores")
                if not df_users.empty and "USUÁRIO" in df_users.columns:
                    user_clean = username.strip().lower()
                    pass_clean = password.strip()
                    
                    df_users["USUÁRIO_CLEAN"] = df_users["USUÁRIO"].astype(str).str.strip().str.lower()
                    df_users["SENHA_CLEAN"] = df_users["SENHA"].astype(str).str.strip()
                    
                    user_row = df_users[(df_users["USUÁRIO_CLEAN"] == user_clean) & (df_users["SENHA_CLEAN"] == pass_clean)]
                    if not user_row.empty:
                        st.session_state["authenticated"] = True
                        st.session_state["user"] = user_row.iloc[0]["NOME"]
                        st.session_state["username_raw"] = user_row.iloc[0]["USUÁRIO"]
                        st.rerun()
                    else:
                        st.error("Usuário ou senha incorretos.")
                else:
                    if (username.strip() == "pedro" and password.strip() == "36950612") or (username.strip() == "fabio" and password.strip() == "admin123"):
                        st.session_state["authenticated"] = True
                        st.session_state["user"] = username
                        st.session_state["username_raw"] = username
                        st.rerun()
                    else:
                        st.error("Erro ao validar dados na planilha.")

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    login()
    st.stop()

# --- REGRAS DE NEGÓCIO E VALIDAÇÃO ---
def validar_agendamento(data, hora_inicio, hora_fim, eh_mensalista):
    dia_semana = data.weekday()
    duracao = (datetime.datetime.combine(data, hora_fim) - datetime.datetime.combine(data, hora_inicio)).seconds / 3600
    
    if duracao < 2:
        return False, "A locação mínima é de 2 horas por banda."
        
    if dia_semana < 5:
        if hora_inicio < datetime.time(18, 0) or (hora_fim > datetime.time(0, 0) and hora_fim != datetime.time(0, 0) and hora_fim < datetime.time(18, 0)):
            return False, "De segunda a sexta o estúdio funciona das 18:00 às 00:00."
    else:
        if hora_inicio < datetime.time(10, 0) or hora_fim > datetime.time(22, 0):
            return False, "Nos finais de semana o estúdio funciona das 10:00 às 22:00."
            
    valor_hora = 60.0 if eh_mensalista else 70.0
    valor_total = duracao * valor_hora
    
    return True, valor_total

def gerar_link_whatsapp(telefone, mensagem):
    tel_limpo = "".join(filter(str.isdigit, str(telefone)))
    if not tel_limpo.startswith("55"):
        tel_limpo = "55" + tel_limpo
    msg_enc = urllib.parse.quote(mensagem)
    return f"https://api.whatsapp.com/send?phone={tel_limpo}&text={msg_enc}"

# --- INTERFACE PRINCIPAL ---
if os.path.exists("logo.png"):
    st.sidebar.image("logo.png", use_container_width=True)
else:
    st.sidebar.markdown("### ⚡ ÓMEGA")

st.sidebar.markdown(f"**Sócio:** {st.session_state['user']}")
if st.sidebar.button("Sair da Sessão", use_container_width=True):
    st.session_state["authenticated"] = False
    st.rerun()

st.sidebar.markdown("---")
aba_opcoes = ["📅 Agenda", "📆 Calendário", "🎸 Clientes", "➕ Novo Ensaio", "💬 WhatsApp", "⚙️ Admin"]
aba = st.sidebar.radio("Menu", aba_opcoes, label_visibility="collapsed")

df_agendamentos = carregar_dados_aba("Agendamentos")
df_blacklist = carregar_dados_aba("Blacklist")
df_clientes = carregar_dados_aba("Clientes")

# --- ABA 1: VER AGENDA ---
if aba == "📅 Agenda":
    col_titulo, col_btn = st.columns([3, 1])
    with col_titulo:
        st.header("📅 Agenda de Ensaios")
    with col_btn:
        st.write("")
        if st.button("Ver Calendário", use_container_width=True):
            st.info("Abra a aba 'Calendário' no menu lateral.")

    data_filtro = st.date_input("Filtrar por data:", datetime.date.today())
    data_str = data_filtro.strftime("%d/%m/%Y")
    
    if not df_agendamentos.empty and "DATA" in df_agendamentos.columns:
        agendamentos_dia = df_agendamentos[df_agendamentos["DATA"].astype(str) == data_str]
        
        if not agendamentos_dia.empty:
            st.subheader(f"Agendamentos para {data_str}:")
            for idx, row in agendamentos_dia.iterrows():
                banda = row.get('NOME DA BANDA', row.get('RESPONSÁVEL', 'Banda'))
                cliente = row.get('NOME DO CLIENTE', '')
                h_inicio = row.get('HORÁRIO INICIAL', '')
                h_fim = row.get('HORÁRIO FINAL', '')
                valor = row.get('VALOR TOTAL', '')
                st.info(f"⏰ **{h_inicio} - {h_fim}** | Banda: **{banda}** ({cliente}) | 💰 {valor}")
        else:
            st.success("Nenhum ensaio agendado para este dia. Sala disponível!")
    else:
        st.success("Nenhum ensaio agendado para este dia. Sala disponível!")

# --- ABA 2: CALENDÁRIO VISUAL COMPLETO ---
elif aba == "📆 Calendário":
    st.header("📆 Visão Geral do Mês")
    st.write("Acompanhe os horários reservados de cada banda de forma limpa e direta:")
    
    events = []
    if not df_agendamentos.empty and "DATA" in df_agendamentos.columns:
        for idx, row in df_agendamentos.iterrows():
            try:
                data_dt = datetime.datetime.strptime(str(row['DATA']), "%d/%m/%Y").strftime("%Y-%m-%d")
                h_ini = str(row['HORÁRIO INICIAL']).strip()
                h_fim = str(row['HORÁRIO FINAL']).strip()
                banda = row.get('NOME DA BANDA', 'Ensaio')
                
                events.append({
                    "title": f"{h_ini} - {h_fim} : {banda}",
                    "start": f"{data_dt}T{h_ini}:00",
                    "end": f"{data_dt}T{h_fim}:00" if h_fim != "00:00" else f"{data_dt}T23:59:59",
                    "color": "#f39c12"
                })
            except Exception as e:
                continue

    calendar_options = {
        "locale": "pt-br",
        "headerToolbar": {
            "left": "prev,next today",
            "center": "title",
            "right": "dayGridMonth,timeGridWeek"
        },
        "buttonText": {
            "today": "Hoje",
            "month": "Mês",
            "week": "Semana"
        },
        "displayEventTime": False,
        "initialView": "dayGridMonth",
        "selectable": True,
        "editable": False,
    }
    
    calendar(events=events, options=calendar_options, key="calendar_estudio_v16")

# --- ABA 3: CADASTRAR CLIENTE ---
elif aba == "🎸 Clientes":
    st.header("🎸 Cadastro de Clientes e Bandas")
    st.write("Adicione novos registros para preenchimento rápido nos agendamentos.")
    
    with st.form("form_cadastrar_cliente"):
        novo_nome_banda = st.text_input("Nome da Banda *")
        novo_nome_cliente = st.text_input("Nome do Cliente / Responsável *")
        novo_whatsapp = st.text_input("Telefone (WhatsApp) *", placeholder="(11) 99999-9999", max_chars=15)
        tipo_cliente = st.selectbox("Tipo de Cliente", ["Avulso", "Mensalista"])
        
        sub_cadastro = st.form_submit_button("Gerar Registro para Planilha", use_container_width=True)
        
        if sub_cadastro:
            tel_digits = "".join(filter(str.isdigit, novo_whatsapp))
            if not novo_nome_banda or not novo_nome_cliente or len(tel_digits) < 10:
                st.error("Por favor, preencha todos os campos obrigatórios corretamente (verifique o telefone com DDD).")
            else:
                if len(tel_digits) == 11:
                    tel_formatado = f"({tel_digits[:2]}) {tel_digits[2:7]}-{tel_digits[7:]}"
                else:
                    tel_formatado = novo_whatsapp

                st.success(f"Registro gerado com sucesso!")
                st.warning("⚠️ Copie a linha abaixo e cole na aba **'Clientes'** da sua Planilha do Google Sheets:")
                st.code(f"{novo_nome_banda}\t{novo_nome_cliente}\t{tel_formatado}\t{tipo_cliente}")

# --- ABA 4: AGENDAR ENSAIO ---
elif aba == "➕ Novo Ensaio":
    st.header("➕ Agendar Novo Ensaio")
    
    opcoes_banda = ["-- Selecionar da base de clientes --"]
    mapa_cadastros = {}
    
    if not df_clientes.empty:
        col_b = "NOME DA BANDA" if "NOME DA BANDA" in df_clientes.columns else df_clientes.columns[0]
        col_c = "NOME DO CLIENTE" if "NOME DO CLIENTE" in df_clientes.columns else df_clientes.columns[1]
        col_t = "TELEFONE" if "TELEFONE" in df_clientes.columns else df_clientes.columns[2]
        
        for idx, r in df_clientes.iterrows():
            b_nome = str(r.get(col_b, '')).strip()
            c_nome = str(r.get(col_c, '')).strip()
            t_num = str(r.get(col_t, '')).strip()
            
            if b_nome and b_nome != 'nan':
                label = f"{b_nome} (Resp: {c_nome})"
                opcoes_banda.append(label)
                mapa_cadastros[label] = {
                    "banda": b_nome,
                    "cliente": c_nome,
                    "telefone": t_num
                }

    col_sel, col_btn_novo = st.columns([3, 1])
    with col_sel:
        banda_selecionada = st.selectbox("Puxar dados do cadastro:", opcoes_banda)
    with col_btn_novo:
        st.write("")
        if st.button("Novo Cadastro", use_container_width=True):
            st.info("Vá em 'Clientes' no menu lateral.")

    val_banda = ""
    val_cliente = ""
    val_telefone = ""
    
    if banda_selecionada != "-- Selecionar da base de clientes --":
        dados_sel = mapa_cadastros[banda_selecionada]
        val_banda = dados_sel["banda"]
        val_cliente = dados_sel["cliente"]
        val_telefone = dados_sel["telefone"]

    with st.form("form_agendamento"):
        nome_banda = st.text_input("Nome da Banda *", value=val_banda)
        nome_cliente = st.text_input("Nome do Cliente *", value=val_cliente)
        telefone_cliente = st.text_input("Telefone (WhatsApp) *", value=val_telefone, placeholder="(11) 99999-9999")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            data = st.date_input("Data do Ensaio *", datetime.date.today())
        with col2:
            hora_inicio = st.time_input("Horário Inicial *", datetime.time(18, 0))
        with col3:
            hora_fim = st.time_input("Horário Final *", datetime.time(20, 0))
            
        eh_mensalista = st.checkbox("Cliente Mensalista (R$ 60/h)")
        forcar_agendamento = st.checkbox("Ignorar alerta de Blacklist (Forçar agendamento)")
        
        submitted = st.form_submit_button("Validar e Confirmar Agendamento", use_container_width=True)
        
        if submitted:
            if not nome_cliente or not telefone_cliente or not nome_banda:
                st.error("Por favor, preencha todos os campos obrigatórios.")
            else:
                bloqueado = False
                motivo_bloqueio = ""
                if not df_blacklist.empty:
                    tel_limpo_input = "".join(filter(str.isdigit, str(telefone_cliente)))
                    for idx, row in df_blacklist.iterrows():
                        banda_bl = str(row.get("NOME DA BANDA", "")).strip().lower()
                        tel_bl = "".join(filter(str.isdigit, str(row.get("TELEFONE", ""))))
                        
                        if (banda_bl and banda_bl == nome_banda.strip().lower()) or (tel_bl and tel_bl == tel_limpo_input):
                            bloqueado = True
                            motivo_bloqueio = row.get("MOTIVO", "Inadimplência ou problemas no estúdio")
                            break
                
                if bloqueado and not forcar_agendamento:
                    st.error(f"⛔ **ATENÇÃO:** O cliente/banda **{nome_banda}** consta na **Blacklist** (Motivo: {motivo_bloqueio}).")
                    st.warning("Se desejar prosseguir, marque a caixa de forçar agendamento acima.")
                else:
                    valido, resultado = validar_agendamento(data, hora_inicio, hora_fim, eh_mensalista)
                    if not valido:
                        st.error(f"Erro no agendamento: {resultado}")
                    else:
                        valor_total = resultado
                        st.success(f"Ensaio validado com sucesso! Valor Total: R$ {valor_total:.2f}")
                        
                        st.warning("⚠️ Copie e cole a linha abaixo na aba **'Agendamentos'** da sua Planilha:")
                        dias_semana_pt = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
                        dia_str = dias_semana_pt[data.weekday()]
                        st.code(f"{data.strftime('%d/%m/%Y')}\t{dia_str}\t{hora_inicio.strftime('%H:%M')}\t{hora_fim.strftime('%H:%M')}\t{nome_cliente}\t{telefone_cliente}\t{nome_banda}\t{'Mensalista' if eh_mensalista else 'Avulso'}\tR$ {valor_total:.2f}\tConfirmado")
                        
                        msg_confirmacao = f"Olá {nome_cliente}! Seu ensaio com a banda {nome_banda} está CONFIRMADO para o dia {data.strftime('%d/%m/%Y')} das {hora_inicio.strftime('%H:%M')} às {hora_fim.strftime('%H:%M')}. Valor: R$ {valor_total:.2f}. Nos vemos no estúdio!"
                        link_wa = gerar_link_whatsapp(telefone_cliente, msg_confirmacao)
                        
                        st.markdown(f"[📲 Enviar Confirmação via WhatsApp]({link_wa})", unsafe_allow_html=True)

# --- ABA 5: DISPAROS WHATSAPP ---
elif aba == "💬 WhatsApp":
    st.header("💬 Lembretes Diários")
    hoje_str = datetime.date.today().strftime("%d/%m/%Y")
    
    if not df_agendamentos.empty and "DATA" in df_agendamentos.columns:
        agendamentos_hoje = df_agendamentos[df_agendamentos["DATA"].astype(str) == hoje_str]
        
        if not agendamentos_hoje.empty:
            for idx, row in agendamentos_hoje.iterrows():
                banda = row.get('NOME DA BANDA', row.get('RESPONSÁVEL', 'Banda'))
                cliente = row.get('NOME DO CLIENTE', 'Cliente')
                h_ini = row.get('HORÁRIO INICIAL', '')
                h_fim = row.get('HORÁRIO FINAL', '')
                tel = row.get('TELEFONE', '')
                
                msg_lembrete = f"Olá {cliente}, lembrete: Hoje é dia de ensaio com a banda {banda} das {h_ini} às {h_fim}. Esperamos vocês!"
                link = gerar_link_whatsapp(tel, msg_lembrete)
                
                st.write(f"🎸 **Banda {banda}** ({h_ini} - {h_fim})")
                st.markdown(f"[📲 Enviar WhatsApp para {cliente}]({link})")
                st.divider()
        else:
            st.info("Não há ensaios marcados para o dia de hoje.")
    else:
        st.info("Não há ensaios marcados para o dia de hoje.")

# --- ABA 6: ADMINISTRAÇÃO ---
elif aba == "⚙️ Admin":
    st.header("⚙️ Painel Administrativo")
    
    sub_tab1, sub_tab2, sub_tab3, sub_tab4 = st.tabs(["Usuários", "Estatísticas", "Finanças", "Blacklist"])
    
    with sub_tab1:
        st.subheader("👥 Gestão de Acessos")
        df_users = carregar_dados_aba("Administradores")
        if not df_users.empty and "USUÁRIO" in df_users.columns:
            st.dataframe(df_users[["USUÁRIO", "NOME"]], use_container_width=True)
            st.info("Para alterar senhas ou adicionar novos sócios, edite diretamente a aba **Administradores** na sua Planilha do Google Sheets.")
        else:
            st.warning("Lista de administradores vazia.")

    with sub_tab2:
        st.subheader("📊 Estatísticas do Estúdio")
        if not df_agendamentos.empty and "DATA" in df_agendamentos.columns:
            df_agendamentos["DT"] = pd.to_datetime(df_agendamentos["DATA"], format="%d/%m/%Y", errors="coerce")
            df_val = df_agendamentos.dropna(subset=["DT"]).copy()
            df_val["MES_ANO"] = df_val["DT"].dt.strftime("%m/%Y")
            df_val["ANO"] = df_val["DT"].dt.strftime("%Y")
            
            meses_disp = sorted(df_val["MES_ANO"].unique().tolist(), reverse=True)
            if meses_disp:
                mes_sel = st.selectbox("Mês de referência:", meses_disp)
                df_mes = df_val[df_val["MES_ANO"] == mes_sel]
                st.metric("Total de Ensaios Realizados", len(df_mes))
                
                st.divider()
                st.write("🏆 **Ranking de Bandas:**")
                ranking = df_mes["NOME DA BANDA"].value_counts().reset_index()
                ranking.columns = ["Nome da Banda", "Quantidade de Ensaios"]
                st.dataframe(ranking, use_container_width=True)
        else:
            st.info("Sem dados para estatísticas.")

    with sub_tab3:
        st.subheader("💰 Faturamento")
        if not df_agendamentos.empty and "DATA" in df_agendamentos.columns:
            df_fin = df_agendamentos.copy()
            df_fin["DT"] = pd.to_datetime(df_fin["DATA"], format="%d/%m/%Y", errors="coerce")
            df_fin = df_fin.dropna(subset=["DT"])
            df_fin["MES_ANO"] = df_fin["DT"].dt.strftime("%m/%Y")
            
            def limpar_valor(v):
                try:
                    v_str = str(v).replace("R$", "").replace(".", "").replace(",", ".").strip()
                    return float(v_str)
                except:
                    return 0.0
                    
            df_fin["VALOR_NUM"] = df_fin["VALOR TOTAL"].apply(limpar_valor)
            resumo_fin = df_fin.groupby("MES_ANO").agg(
                TOTAL_ENSAIOS=("VALOR_NUM", "count"),
                VALOR_BRUTO_ESTIMADO=("VALOR_NUM", "sum")
            ).reset_index()
            
            resumo_fin["VALOR BRUTO"] = resumo_fin["VALOR_BRUTO_ESTIMADO"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            st.dataframe(resumo_fin[["MES_ANO", "TOTAL_ENSAIOS", "VALOR BRUTO"]], use_container_width=True)
        else:
            st.info("Sem dados financeiros.")

    with sub_tab4:
        st.subheader("🚫 Blacklist")
        if not df_blacklist.empty:
            st.dataframe(df_blacklist, use_container_width=True)
        else:
            st.info("Nenhuma banda na Blacklist.")
            
        st.divider()
        with st.form("form_blacklist"):
            bl_banda = st.text_input("Banda *")
            bl_cliente = st.text_input("Cliente / Responsável *")
            bl_tel = st.text_input("Telefone *", placeholder="(11) 99999-9999")
            bl_data = st.date_input("Data do Ocorrido *", datetime.date.today())
            bl_motivo = st.text_input("Motivo", value="Falta sem aviso")
            
            sub_bl = st.form_submit_button("Gerar Linha Blacklist", use_container_width=True)
            if sub_bl:
                if not bl_banda or not bl_cliente or not bl_tel:
                    st.error("Preencha os campos obrigatórios.")
                else:
                    st.success("Gerado com sucesso! Copie a linha para a aba Blacklist da planilha:")
                    st.code(f"{bl_banda}\t{bl_cliente}\t{bl_tel}\t{bl_data.strftime('%d/%m/%Y')}\t{bl_motivo}")
