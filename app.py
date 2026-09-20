import streamlit as st
import datetime
import pandas as pd
import urllib.parse

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gestão de Ensaio - Estúdio", page_icon="🎵", layout="centered")

# --- LOGIN DOS SÓCIOS ---
USERS = {
    "socio1": "senha123",
    "socio2": "senha456"
}

def login():
    st.title("🔑 Login - Estúdio de Música")
    username = st.text_input("Usuário")
    password = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        if username in USERS and USERS[username] == password:
            st.session_state["authenticated"] = True
            st.session_state["user"] = username
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos.")

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
        if hora_inicio < datetime.time(18, 0) or hora_fim > datetime.time(0, 0) and hora_fim != datetime.time(0, 0):
            return False, "De segunda a sexta o estúdio funciona das 18:00 às 00:00."
    else: # Fim de semana
        if hora_inicio < datetime.time(10, 0) or hora_fim > datetime.time(22, 0):
            return False, "Nos finais de semana o estúdio funciona das 10:00 às 22:00."
            
    # Preço
    valor_hora = 60.0 if eh_mensalista else 70.0
    valor_total = duracao * valor_hora
    
    return True, valor_total

# --- FUNÇÃO DE MENSAGENS WHATSAPP ---
def gerar_link_whatsapp(telefone, mensagem):
    # Remove caracteres não numéricos do telefone
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

# Simulação de Base de Dados (Conectar ao Google Sheets via gspread em produção)
if "agendamentos" not in st.session_state:
    st.session_state["agendamentos"] = pd.DataFrame([
        {"Data": "2026-09-01", "Início": "21:00", "Fim": "23:00", "Cliente": "Star Lord", "Banda": "Star Lord", "Telefone": "11999999999", "Tipo": "Avulso", "Valor": 140.0},
        {"Data": "2026-09-05", "Início": "10:00", "Fim": "12:00", "Cliente": "Duzeck", "Banda": "Duzeck", "Telefone": "11988888888", "Tipo": "Avulso", "Valor": 140.0}
    ])

# --- ABA 1: VER AGENDA ---
if aba == "📅 Ver Agenda":
    st.header("📅 Agenda de Ensaios")
    data_filtro = st.date_input("Filtrar por data:", datetime.date.today())
    
    df = st.session_state["agendamentos"]
    agendamentos_dia = df[df["Data"] == str(data_filtro)]
    
    if not agendamentos_dia.empty:
        st.subheader(f"Agendamentos para {data_filtro.strftime('%d/%m/%Y')}:")
        for idx, row in agendamentos_dia.iterrows():
            st.info(f"⏰ **{row['Início']} - {row['Fim']}** | Banda: **{row['Banda']}** ({row['Cliente']}) | 💰 R$ {row['Valor']:.2f}")
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
                    novo_agendamento = {
                        "Data": str(data),
                        "Início": hora_inicio.strftime("%H:%M"),
                        "Fim": hora_fim.strftime("%H:%M"),
                        "Cliente": nome_cliente,
                        "Banda": nome_banda,
                        "Telefone": telefone_cliente,
                        "Tipo": "Mensalista" if eh_mensalista else "Avulso",
                        "Valor": valor_total
                    }
                    st.session_state["agendamentos"] = pd.concat([st.session_state["agendamentos"], pd.DataFrame([novo_agendamento])], ignore_index=True)
                    st.success(f"Ensaio agendado com sucesso! Valor Total: R$ {valor_total:.2f}")
                    
                    # Gerar mensagem de confirmação para o WhatsApp
                    msg_confirmacao = f"Olá {nome_cliente}! Seus ensaio com a banda {nome_banda} está CONFIRMADO para o dia {data.strftime('%d/%m/%Y')} das {hora_inicio.strftime('%H:%M')} às {hora_fim.strftime('%H:%M')}. Valor: R$ {valor_total:.2f}. Nos vemos no estúdio!"
                    link_wa = gerar_link_whatsapp(telefone_cliente, msg_confirmacao)
                    
                    st.markdown(f"[📲 Enviar Confirmação via WhatsApp]({link_wa})", unsafe_allow_html=True)

# --- ABA 3: DISPAROS WHATSAPP ---
elif aba == "💬 Disparos WhatsApp":
    st.header("💬 Lembrete do Dia")
    st.write("Envie a mensagem de lembrete do dia com apenas 1 clique.")
    
    hoje_str = str(datetime.date.today())
    df = st.session_state["agendamentos"]
    agendamentos_hoje = df[df["Data"] == hoje_str]
    
    if not agendamentos_hoje.empty:
        for idx, row in agendamentos_hoje.iterrows():
            msg_lembrete = f"Olá {row['Cliente']}, lembrete: Hoje é dia de ensaio com a banda {row['Banda']} das {row['Início']} às {row['Fim']}. Esperamos vocês!"
            link = gerar_link_whatsapp(row["Telefone"], msg_lembrete)
            
            st.write(f"🎸 **Banda {row['Banda']}** ({row['Início']} - {row['Fim']})")
            st.markdown(f"[📲 Enviar WhatsApp para {row['Cliente']}]({link})")
            st.divider()
    else:
        st.info("Não há ensaios marcados para o dia de hoje.")
