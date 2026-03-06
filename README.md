# Liga Bot

Um bot do Discord para gerenciar ligas e jogos competitivos.

## Funcionalidades

- Sistema de ranking
- Lobby e matchmaking
- Comandos administrativos
- Loja de itens
- Sistema VIP
- E muito mais!

## Instalação

1. Clone o repositório:
   ```
   git clone https://github.com/seu-usuario/liga-bot.git
   cd liga-bot
   ```

2. Crie um ambiente virtual:
   ```
   python -m venv .venv
   .venv\Scripts\activate  # No Windows
   ```

3. Instale as dependências:
   ```
   pip install -r requirements.txt
   ```

4. Configure as variáveis de ambiente:
   - Copie `.env.example` para `.env`
   - Preencha com suas configurações (token do Discord, banco de dados, etc.)

5. Execute o bot:
   ```
   python main.py
   ```

## Configuração

O bot usa variáveis de ambiente para configuração. Veja o arquivo `src/core/config.py` para detalhes.

### Banco de Dados

O bot usa PostgreSQL. Configure as variáveis `POSTGRES_*` no `.env`.

## Contribuição

Contribuições são bem-vindas! Abra uma issue ou pull request.

## Licença

Este projeto está licenciado sob a MIT License - veja o arquivo [LICENSE](LICENSE) para detalhes.