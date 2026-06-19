# Guia de Implantação: Servidor Apache na AWS (EC2)

Este guia orienta na hospedagem deste aplicativo Flask (Cashbills) em uma instância AWS EC2 executando o servidor web **Apache** como um Proxy Reverso, utilizando o **Gunicorn** como servidor de aplicação WSGI.

---

## Pré-requisitos

1. **Instância AWS EC2**: Recomendado utilizar **Ubuntu Server 22.04 LTS** ou posterior.
2. **Security Group na AWS**: Certifique-se de liberar as portas de entrada:
   - `80` (HTTP) - Acesso público
   - `443` (HTTPS) - Acesso seguro SSL (opcional)
   - `22` (SSH) - Para administração do servidor

---

## Passo 1: Acessar a Instância e Atualizar o Sistema

Acesse a sua máquina via terminal SSH e atualize a lista de pacotes:

```bash
ssh -i "seu-par-de-chaves.pem" ubuntu@seu-ip-publico-ec2
sudo apt update && sudo apt upgrade -y
```

---

## Passo 2: Instalar o Apache, Python e Dependências

Instale o Apache, o gerenciador de pacotes pip e as ferramentas de ambiente virtual do Python:

```bash
sudo apt install -y apache2 python3-pip python3-venv python3-dev git
```

---

## Passo 3: Clonar e Preparar a Aplicação

1. Recomendamos organizar os arquivos da aplicação no diretório `/var/www/cashbills`:

   ```bash
   sudo mkdir -p /var/www/cashbills
   sudo chown -R ubuntu:ubuntu /var/www/cashbills
   cd /var/www/cashbills
   ```

2. Coloque os códigos do projeto nesta pasta (via Git clone, SFTP, etc.). O diretório deve conter:
   - `app.py`
   - `modelo.yaml`
   - `requirements.txt`
   - `templates/index.html`

3. Crie e ative um ambiente virtual Python:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

4. Instale as dependências listadas no `requirements.txt` e o `gunicorn`:

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   pip install gunicorn
   ```

---

## Passo 4: Configurar o Gunicorn com o Systemd

Para garantir que o servidor da aplicação Python rode em segundo plano e reinicie caso a máquina seja desligada, criaremos um serviço do sistema.

1. Crie o arquivo de serviço:

   ```bash
   sudo nano /etc/systemd/system/cashbills.service
   ```

2. Cole a seguinte configuração (certifique-se de que os caminhos coincidem com a sua instalação):

   ```ini
   [Unit]
   Description=Servico Gunicorn para Cashbills
   After=network.target

   [Service]
   User=ubuntu
   WorkingDirectory=/var/www/cashbills
   Environment="PATH=/var/www/cashbills/.venv/bin"
   ExecStart=/var/www/cashbills/.venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 app:app

   [Install]
   WantedBy=multi-user.target
   ```

3. Salve o arquivo (`Ctrl+O`, `Enter`, `Ctrl+X`) e inicialize o serviço:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl start cashbills
   sudo systemctl enable cashbills
   ```

4. Verifique se o serviço está executando corretamente:

   ```bash
   sudo systemctl status cashbills
   ```

---

## Passo 5: Configurar o Apache como Proxy Reverso

Agora configuramos o Apache para receber requisições nas portas 80/443 e repassá-las internamente para o Gunicorn (na porta 5000).

1. Habilite os módulos de proxy do Apache:

   ```bash
   sudo a2enmod proxy
   sudo a2enmod proxy_http
   sudo a2enmod headers
   ```

2. Crie um novo arquivo de configuração do site:

   ```bash
   sudo nano /etc/apache2/sites-available/cashbills.conf
   ```

3. Adicione o seguinte bloco de configuração (substituindo `seu_dominio.com` ou o IP público):

   ```apache
   <VirtualHost *:80>
       ServerName seu_dominio.com
       # Ou use o IP caso nao possua dominio configurado:
       # ServerAdmin webmaster@localhost

       ProxyPreserveHost On
       ProxyPass / http://127.0.0.1:5000/
       ProxyPassReverse / http://127.0.0.1:5000/

       ErrorLog ${APACHE_LOG_DIR}/cashbills_error.log
       CustomLog ${APACHE_LOG_DIR}/cashbills_access.log combined
   </VirtualHost>
   ```

4. Desative a página padrão do Apache e ative o seu site:

   ```bash
   sudo a2dissite 000-default.conf
   sudo a2ensite cashbills.conf
   ```

5. Teste a sintaxe das configurações do Apache:

   ```bash
   sudo apache2ctl configtest
   ```
   *(Deve retornar "Syntax OK")*

6. Reinicie o Apache para aplicar as mudanças:

   ```bash
   sudo systemctl restart apache2
   ```

---

## Passo 6: Testar a Implantação

Abra o seu navegador e acesse o endereço IP público da sua instância AWS EC2 (ou o seu domínio):
`http://seu-ip-publico-ec2`

Seu painel financeiro Cashbills deverá estar carregado com os dados estilizados e pronto para uso!

### Atualizando os Dados
Sempre que você quiser atualizar as informações financeiras:
1. Edite o arquivo local `/var/www/cashbills/modelo.yaml`.
2. Como o Flask lerá o arquivo YAML a cada requisição (a função `load_data` é executada na rota `/`), as alterações refletirão imediatamente na interface sem necessidade de reiniciar o serviço.
