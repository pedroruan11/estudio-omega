import streamlit as st
import datetime
import pandas as pd
import urllib.parse
import os
from streamlit_calendar import calendar

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gestão de Ensaio - Estúdio Ómega", page_icon="🎵", layout="wide")

# CSS Personalizado para o Calendário e Elementos da Interface
st.markdown("""
<style>
    .fc-daygrid-event-dot {
        display: none !important;
    }
    .fc-event-title {
        font-size: 11px !important;
        font-weight: 500 !important;
        white-space: normal !important;
    }
    .fc-event {
        padding: 1px 3px !important;
        margin-bottom: 2px !important;
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
    # Se a logo existir, exibe na tela de login
    if os.path.exists("logo.png"):
        st.image("logo.png", width=200)
    else:
        st.title("🔑 Login - Estúdio Ómega")
        
    username = st.text_input("Usuário")
    password = st.text_input("Senha", type="password")
    
    if st.button("Entrar"):
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
# Exibir Logo na Barra Lateral se o arquivo existir
if os.path.exists("logo.png"):
    st.sidebar.image("logo.png", use_container_width=True)

st.sidebar.title(f"Bem-vindo, {st.session_state['user']}")
if st.sidebar.button("Sair"):
    st.session_state["authenticated"] = False
    st.rerun()

aba = st.sidebar.radio("Navegação", ["📅 Ver Agenda", "📆 Calendário Mensal", "➕ Agendar Ensaio", "💬 Disparos WhatsApp", "⚙️ Administração"])

df_agendamentos = carregar_dados_aba("Agendamentos")
df_blacklist = carregar_dados_aba("Blacklist")

# --- ABA 1: VER AGENDA ---
if aba == "📅 Ver Agenda":
    col_titulo, col_btn = st.columns([3, 1])
    with col_titulo:
        st.header("📅 Agenda de Ensaios")
    with col_btn:
        st.write("")
        if st.button("📆 Ver Calendário Completo", type="primary"):
            st.info("Acesse a aba '📆 Calendário Mensal' no menu lateral para visualizar o mês completo!")

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
elif aba == "📆 Calendário Mensal":
    st.header("📆 Visão Geral do Calendário")
    st.write("Acompanhe os dias ocupados e os horários reservados de cada banda:")
    
    events = []
    if not df_agendamentos.empty and "DATA" in df_agendamentos.columns:
        for idx, row in df_agendamentos.iterrows():
            try:
                data_dt = datetime.datetime.strptime(str(row['DATA']), "%d/%m/%Y").strftime("%Y-%m-%d")
                h_ini = str(row['HORÁRIO INICIAL']).strip()
                h_fim = str(row['HORÁRIO FINAL']).strip()
                banda = row.get('NOME DA BANDA', 'Ensaio')
                
                events.append({
                    "title": f"{h_ini} - {h_fim} - {banda}",
                    "start": f"{data_dt}T{h_ini}:00",
                    "end": f"{data_dt}T{h_fim}:00" if h_fim != "00:00" else f"{data_dt}T23:59:59",
                    "color": "#1f77b4"
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
    
    calendar(events=events, options=calendar_options, key="calendar_estudio_v7")

# --- ABA 3: AGENDAR ENSAIO ---
elif aba == "➕ Agendar Ensaio":
    st.header("➕ Novo Agendamento")
    
    with st.form("form_agendamento"):
        nome_cliente = st.text_input("Nome do Cliente *")
        telefone_cliente = st.text_input("Telefone (WhatsApp) *", placeholder="11976297814")
        nome_banda = st.text_input("Nome da Banda *")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            data = st.date_input("Data do Ensaio *", datetime.date.today())
        with col2:
            hora_inicio = st.time_input("Horário Inicial *", datetime.time(18, 0))
        with col3:
            hora_fim = st.time_input("Horário Final *", datetime.time(20, 0))
            
        eh_mensalista = st.checkbox("Cliente Mensalista (R$ 60/h)")
        forcar_agendamento = st.checkbox("Ignorar alerta de Blacklist e prosseguir mesmo assim")
        
        submitted = st.form_submit_button("Confirmar Agendamento")
        
        if submitted:
            if not nome_cliente or not telefone_cliente or not nome_banda:
                st.error("Por favor, preencha todos os campos obrigatórios.")
            else:
                # Verificar Blacklist
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
                    st.warning("Se desejar agendar mesmo assim, marque a caixa **'Ignorar alerta de Blacklist e prosseguir mesmo assim'** acima e confirme novamente.")
                else:
                    valido, resultado = validar_agendamento(data, hora_inicio, hora_fim, eh_mensalista)
                    if not valido:
                        st.error(f"Erro no agendamento: {resultado}")
                    else:
                        valor_total = resultado
                        st.success(f"Ensaio validado com sucesso! Valor Total: R$ {valor_total:.2f}")
                        
                        st.warning("⚠️ Cole a linha abaixo na sua Planilha do Google Sheets (Aba 'Agendamentos'):")
                        dias_semana_pt = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
                        dia_str = dias_semana_pt[data.weekday()]
                        st.code(f"{data.strftime('%d/%m/%Y')}\t{dia_str}\t{hora_inicio.strftime('%H:%M')}\t{hora_fim.strftime('%H:%M')}\t{nome_cliente}\t{telefone_cliente}\t{nome_banda}\t{'Mensalista' if eh_mensalista else 'Avulso'}\tR$ {valor_total:.2f}\tConfirmado")
                        
                        msg_confirmacao = f"Olá {nome_cliente}! Seu ensaio com a banda {nome_banda} está CONFIRMADO para o dia {data.strftime('%d/%m/%Y')} das {hora_inicio.strftime('%H:%M')} às {hora_fim.strftime('%H:%M')}. Valor: R$ {valor_total:.2f}. Nos vemos no estúdio!"
                        link_wa = gerar_link_whatsapp(telefone_cliente, msg_confirmacao)
                        
                        st.markdown(f"[📲 Enviar Confirmação via WhatsApp]({link_wa})", unsafe_allow_html=True)

# --- ABA 4: DISPAROS WHATSAPP ---
elif aba == "💬 Disparos WhatsApp":
    st.header("💬 Lembrete do Dia")
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

# --- ABA 5: ADMINISTRAÇÃO ---
elif aba == "⚙️ Administração":
    st.header("⚙️ Painel de Administração")
    
    sub_tab1, sub_tab2, sub_tab3, sub_tab4 = st.tabs(["👥 Gerenciar Usuários", "📊 Estatísticas", "💰 Finanças", "🚫 Blacklist"])
    
    # --- 1. GERENCIAR USUÁRIOS ---
    with sub_tab1:
        st.subheader("👥 Gerenciar Usuários & Alterar Senha")
        df_users = carregar_dados_aba("Administradores")
        
        if not df_users.empty and "USUÁRIO" in df_users.columns:
            st.dataframe(df_users[["USUÁRIO", "NOME"]], use_container_width=True)
            
            st.divider()
            st.write("🔒 **Instruções para Alterar Senha:**")
            st.info("Para alterar a sua senha ou adicionar um novo sócio, abra a aba **Administradores** na sua Planilha do Google Drive e edite diretamente a coluna **SENHA**.")
            st.markdown(f"[📂 Abrir Planilha 'Administradores' no Google Drive](https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=0)", unsafe_allow_html=True)
        else:
            st.warning("Não foi possível carregar a lista de administradores.")

    # --- 2. ESTATÍSTICAS ---
    with sub_tab2:
        st.subheader("📊 Estatísticas do Estúdio")
        
        if not df_agendamentos.empty and "DATA" in df_agendamentos.columns:
            df_agendamentos["DT"] = pd.to_datetime(df_agendamentos["DATA"], format="%d/%m/%Y", errors="coerce")
            df_val = df_agendamentos.dropna(subset=["DT"]).copy()
            
            df_val["MES_ANO"] = df_val["DT"].dt.strftime("%m/%Y")
            df_val["ANO"] = df_val["DT"].dt.strftime("%Y")
            
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                meses_disp = sorted(df_val["MES_ANO"].unique().tolist(), reverse=True)
                mes_sel = st.selectbox("Filtrar Estatísticas por Mês:", meses_disp)
            
            df_mes = df_val[df_val["MES_ANO"] == mes_sel]
            
            st.metric("Total de Ensaios no Mês Selecionado", len(df_mes))
            
            st.divider()
            st.subheader("🏆 Ranking de Bandas que Mais Ensaiarem")
            
            tipo_ranking = st.radio("Visualizar Ranking por:", ["Por Mês", "Por Ano"], horizontal=True)
            
            if tipo_ranking == "Por Mês":
                ranking = df_mes["NOME DA BANDA"].value_counts().reset_index()
                ranking.columns = ["Nome da Banda", "Quantidade de Ensaios"]
                st.dataframe(ranking, use_container_width=True)
            else:
                ano_sel = mes_sel.split("/")[1]
                df_ano = df_val[df_val["ANO"] == ano_sel]
                ranking_ano = df_ano["NOME DA BANDA"].value_counts().reset_index()
                ranking_ano.columns = ["Nome da Banda", "Quantidade de Ensaios no Ano"]
                st.dataframe(ranking_ano, use_container_width=True)
        else:
            st.info("Sem dados de agendamento disponíveis para estatísticas.")

    # --- 3. FINANÇAS ---
    with sub_tab3:
        st.subheader("💰 Faturamento Consolidado")
        
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
            
            resumo_fin["MÉDIA / VALOR BRUTO ESTIMADO"] = resumo_fin["VALOR_BRUTO_ESTIMADO"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            
            st.write("📊 **Resumo de Arrecadação por Mês:**")
            st.caption("Nota: Os valores são calculados com base no preço padrão das locações (Média Estimada), sem considerar eventuais descontos concedidos no momento do pagamento.")
            st.dataframe(resumo_fin[["MES_ANO", "TOTAL_ENSAIOS", "MÉDIA / VALOR BRUTO ESTIMADO"]], use_container_width=True)
        else:
            st.info("Sem dados financeiros disponíveis.")

    # --- 4. BLACKLIST ---
    with sub_tab4:
        st.subheader("🚫 Gestão de Blacklist (Inadimplentes)")
        
        if not df_blacklist.empty:
            st.write("📋 **Bandas Atualmente na Blacklist:**")
            st.dataframe(df_blacklist, use_container_width=True)
        else:
            st.info("Nenhuma banda registrada na Blacklist até o momento.")
            
        st.divider()
        st.write("➕ **Adicionar Linha na Blacklist (Copiar para a Planilha):**")
        
        with st.form("form_blacklist"):
            bl_banda = st.text_input("Nome da Banda *")
            bl_cliente = st.text_input("Nome do Cliente / Responsável *")
            bl_tel = st.text_input("Telefone (WhatsApp) *", placeholder="11976297814")
            bl_data = st.date_input("Data do Ocorrido / Falta *", datetime.date.today())
            bl_motivo = st.text_input("Motivo", value="Falta sem aviso / Inadimplência")
            
            sub_bl = st.form_submit_button("Gerar Registro de Blacklist")
            
            if sub_bl:
                if not bl_banda or not bl_cliente or not bl_tel:
                    st.error("Preencha todos os campos obrigatórios.")
                else:
                    st.success("Linha gerada com sucesso!")
                    st.warning("⚠️ Copie o texto abaixo e cole na aba **'Blacklist'** da sua Planilha do Google Drive:")
                    st.code(f"{bl_banda}\t{bl_cliente}\t{bl_tel}\t{bl_data.strftime('%d/%m/%Y')}\t{bl_motivo}")
