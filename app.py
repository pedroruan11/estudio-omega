import streamlit as st
import datetime
import pandas as pd
import urllib.parse

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gestão de Ensaio - Estúdio Ómega", page_icon="🎵", layout="centered")

# ID da Planilha do Google Sheets
SHEET_ID = "1Cpz09lM3tPnx1kG2pk4UAKR3bgIQ8WPmMJnRP6EpLEY"

# --- CARREGAR DADOS DA PLANILHA ---
@st.cache_data(ttl=10)
def carregar_dados_aba(nome_aba):
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={nome_aba}"
    try:
        return pd.read_csv(url)
    except Exception as e:
        return pd.DataFrame()

# --- LOGIN DOS SÓCIOS ---
def login():
    st.title("🔑 Login - Estúdio Ómega")
    username = st.text_input("Usuário")
    password = st.text_input("Senha", type="password")
    
    if st.button("Entrar"):
        df_users = carregar_dados_aba("Administradores")
        if not df_users.empty and "USUÁRIO" in df_users.columns:
            user_row = df_users[(df_users["USUÁRIO"].astype(str) == username) & (df_users["SENHA"].astype(str) == password)]
            if not user_row.empty:
                st.session_state["authenticated"] = True
                st.session_state["user"] = user_row.iloc[0]["NOME"]
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")
        else:
            # Fallback de emergência para primeiro acesso
            if (username == "socio1" and password == "senha123") or (username == "socio2" and password == "senha456"):
                st.session_state["authenticated"] = True
                st.session_state["user"] = username
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
    dia_semana = data.weekday() # 0-4: Segunda a Sexta, 5-6: Sábado e Domingo
    
    # Duração em horas
    duracao = (datetime.datetime.combine(data, hora_fim) - datetime.datetime.combine(data, hora_inicio)).seconds / 3600
    
    if duracao < 2:
        return False, "A locação mínima é de 2 horas por banda."
        
    # Validar Horário de Funcionamento
    if dia_semana < 5: # Segunda a Sexta
        if hora_inicio < datetime.time(18, 0) or (hora_fim > datetime.time(0, 0) and hora_fim != datetime.time(0, 0) and hora_fim < datetime.time(18, 0)):
            return False, "De segunda a sexta o estúdio funciona das 18:00 às 00:00."
    else: # Fim de semana
        if hora_inicio < datetime.time(10, 0) or hora_fim > datetime.time(22, 0):
            return False, "Nos finais de semana o estúdio funciona das 10:00 às 22:00."
            
    # Preço
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
st.sidebar.title(f"Bem-vindo, {st.session_state['user']}")
if st.sidebar.button("Sair"):
    st.session_state["authenticated"] = False
    st.rerun()

aba = st.sidebar.radio("Navegação", ["📅 Ver Agenda", "➕ Agendar Ensaio", "💬 Disparos WhatsApp"])

df_agendamentos = carregar_dados_aba("Agendamentos")

# --- ABA 1: VER AGENDA ---
if aba == "📅 Ver Agenda":
    st.header("📅 Agenda de Ensaios")
    data_filtro = st.date_input("Filtrar por data:", datetime.date.today())
    data_str = data_filtro.strftime("%d/%m/%Y")
    
    if not df_agendamentos.empty and "DATA" in df_agendamentos.columns:
        agendamentos_dia = df_agendamentos[df_agendamentos["DATA"].astype(str) == data_str]
        
        if not agendamentos_dia.empty:
            st.subheader(f"Agendamentos para {data_str}:")
            for idx, row in agendamentos_dia.iterrows():
                st.info(f"⏰ **{row['HORÁRIO INICIAL']} - {row['HORÁRIO FINAL']}** | Banda: **{row['NOME DA BANDA']}** ({row['NOME DO CLIENTE']}) | 💰 {row['VALOR TOTAL']}")
        else:
            st.success("Nenhum ensaio agendado para este dia. Sala disponível!")
    else:
        st.success("Nenhum ensaio agendado para este dia. Sala disponível!")

# --- ABA 2: AGENDAR ENSAIO ---
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
        
        submitted = st.form_submit_button("Confirmar Agendamento")
        
        if submitted:
            if not nome_cliente or not telefone_cliente or not nome_banda:
                st.error("Por favor, preencha todos os campos obrigatórios.")
            else:
                valido, resultado = validar_agendamento(data, hora_inicio, hora_fim, eh_mensalista)
                if not valido:
                    st.error(f"Erro no agendamento: {resultado}")
                else:
                    valor_total = resultado
                    st.success(f"Ensaio validado! Valor Total: R$ {valor_total:.2f}")
                    
                    # Link para o usuário adicionar na planilha
                    st.warning("⚠️ Adicione a linha abaixo na sua Planilha do Google Sheets para salvar:")
                    dias_semana_pt = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
                    dia_str = dias_semana_pt[data.weekday()]
                    st.code(f"{data.strftime('%d/%m/%Y')}\t{dia_str}\t{hora_inicio.strftime('%H:%M')}\t{hora_fim.strftime('%H:%M')}\t{nome_cliente}\t{telefone_cliente}\t{nome_banda}\t{'Mensalista' if eh_mensalista else 'Avulso'}\tR$ {valor_total:.2f}\tConfirmado")
                    
                    msg_confirmacao = f"Olá {nome_cliente}! Seus ensaio com a banda {nome_banda} está CONFIRMADO para o dia {data.strftime('%d/%m/%Y')} das {hora_inicio.strftime('%H:%M')} às {hora_fim.strftime('%H:%M')}. Valor: R$ {valor_total:.2f}. Nos vemos no estúdio!"
                    link_wa = gerar_link_whatsapp(telefone_cliente, msg_confirmacao)
                    
                    st.markdown(f"[📲 Enviar Confirmação via WhatsApp]({link_wa})", unsafe_allow_html=True)

# --- ABA 3: DISPAROS WHATSAPP ---
elif aba == "💬 Disparos WhatsApp":
    st.header("💬 Lembrete do Dia")
    hoje_str = datetime.date.today().strftime("%d/%m/%Y")
    
    if not df_agendamentos.empty and "DATA" in df_agendamentos.columns:
        agendamentos_hoje = df_agendamentos[df_agendamentos["DATA"].astype(str) == hoje_str]
        
        if not agendamentos_hoje.empty:
            for idx, row in agendamentos_hoje.iterrows():
                msg_lembrete = f"Olá {row['NOME DO CLIENTE']}, lembrete: Hoje é dia de ensaio com a banda {row['NOME DA BANDA']} das {row['HORÁRIO INICIAL']} às {row['HORÁRIO FINAL']}. Esperamos vocês!"
                link = gerar_link_whatsapp(row["TELEFONE"], msg_lembrete)
                
                st.write(f"🎸 **Banda {row['NOME DA BANDA']}** ({row['HORÁRIO INICIAL']} - {row['HORÁRIO FINAL']})")
                st.markdown(f"[📲 Enviar WhatsApp para {row['NOME DO CLIENTE']}]({link})")
                st.divider()
        else:
            st.info("Não há ensaios marcados para o dia de hoje.")
    else:
        st.info("Não há ensaios marcados para o dia de hoje.")
