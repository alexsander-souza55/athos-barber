# Prospect BarberHub

Sistema web de gestão para barbearias pequenas — simples, moderno e responsivo.

## Stack

| Camada | Tecnologia |
|--------|-----------|
| Backend | Python 3.12 · Flask 3 · Flask-SQLAlchemy · Flask-Login |
| Frontend | Jinja2 · Bootstrap 5 · Chart.js |
| Banco | SQLite (migração fácil para PostgreSQL) |
| Relatórios | Pandas · OpenPyXL |

## Funcionalidades

- **Agendamentos** — criação, atualização de status, filtros por data
- **Barbeiros** — cadastro com foto, controle ativo/inativo
- **Clientes** — histórico de visitas, busca, detalhes
- **Serviços** — preço, duração, ativar/desativar
- **Dashboard** — métricas do dia/semana e gráfico de receita (Chart.js)
- **Sorteios** — inscrição de clientes e sorteio aleatório
- **Relatórios** — exportação para Excel (.xlsx) e CSV
- **Autenticação** — admin (acesso total) e barbeiro (apenas próprios agendamentos)

## Instalação

```bash
# 1. Clone e entre na pasta
cd barber_prospect

# 2. Crie e ative o virtualenv
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # Linux/Mac

# 3. Instale dependências
pip install -r requirements.txt

# 4. Configure o ambiente
copy .env.example .env
# Edite .env e defina um SECRET_KEY forte

# 5. Inicialize o banco
flask --app run init-db

# 6. Popule dados iniciais
flask --app run seed

# 7. Rode o servidor
python run.py
```

Acesse: **http://localhost:5000**

Credenciais padrão:
- Admin: `admin` / `admin123`
- Barbeiro: `joao` / `barber123`

> **Mude as senhas em produção!**

## Estrutura do projeto

```
barber_prospect/
├── app/
│   ├── auth/           # Login, logout, troca de senha
│   ├── appointments/   # Agendamentos (CRUD + status)
│   ├── barbers/        # Gestão de barbeiros
│   ├── customers/      # Gestão de clientes
│   ├── dashboard/      # Métricas e gráficos
│   ├── raffle/         # Sorteios de clientes
│   ├── reports/        # Exportação de relatórios
│   ├── services/       # Serviços e preços
│   ├── models/         # SQLAlchemy ORM (User, Barber, Customer, Service, Appointment, Raffle)
│   ├── utils/          # Decorators (admin_required) e helpers (upload)
│   ├── templates/      # Jinja2 por blueprint
│   ├── static/         # CSS, JS, imagens, uploads
│   ├── extensions.py   # db, login_manager
│   └── config.py       # Configurações por ambiente
├── run.py              # Entry point + CLI (init-db, seed)
├── requirements.txt
└── .env.example
```

## Arquitetura

**MVC com Blueprints Flask:**
- **Model** → `app/models/` (SQLAlchemy, lógica de domínio nas propriedades)
- **View** → `app/templates/` (Jinja2, um diretório por blueprint)
- **Controller** → `app/<blueprint>/routes.py` (lógica HTTP, sem regras de negócio complexas)

**Decisões de design:**
- `extensions.py` separa `db` e `login_manager` para evitar circular imports
- Factory function `create_app()` permite múltiplos contextos (test, prod)
- Formulários sensíveis usam Flask-WTF (CSRF automático)
- Formulários simples usam HTML puro (menos boilerplate)
- `admin_required` decorator garante controle de acesso declarativo
- SQLite em dev → troca por `DATABASE_URL=postgresql://...` em prod sem mudança de código

## Próximos passos sugeridos

- [ ] Agendamento público (sem login) para clientes
- [ ] Notificações por WhatsApp/SMS
- [ ] Calendário visual (FullCalendar.js)
- [ ] Relatório de faturamento por barbeiro
- [ ] Migração para PostgreSQL em produção
- [ ] Deploy no Railway ou Render
