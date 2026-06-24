import os
import datetime
import yaml
from flask import Flask, render_template, request, abort, redirect, url_for

app = Flask(__name__)

YAML_PATH = os.path.join(os.path.dirname(__file__), 'modelo.yaml')

def format_currency(val):
    if val is None:
        val = 0.0
    s = f"{val:,.2f}"
    # Swap comma and dot for PT-BR formatting: "1,234.56" -> "1.234,56"
    parts = s.split('.')
    main = parts[0].replace(',', '.')
    cents = parts[1]
    return f"R$ {main},{cents}"

def get_days_until_next_5th():
    today = datetime.date.today()
    if today.day < 5:
        target_date = datetime.date(today.year, today.month, 5)
    else:
        if today.month == 12:
            target_date = datetime.date(today.year + 1, 1, 5)
        else:
            target_date = datetime.date(today.year, today.month + 1, 5)
    delta = (target_date - today).days
    return max(1, delta)

def load_data():
    if not os.path.exists(YAML_PATH):
        return {"periodos": []}
    with open(YAML_PATH, 'r', encoding='utf-8') as f:
        try:
            return yaml.safe_load(f) or {"periodos": []}
        except Exception as e:
            app.logger.error(f"Error reading YAML: {e}")
            return {"periodos": []}

def generate_periods():
    # Start at 2026-01
    start_year = 2026
    start_month = 1
    
    # Get current year and month
    today = datetime.date.today()
    curr_year = today.year
    curr_month = today.month
    
    # Next month (future period)
    if curr_month == 12:
        next_year = curr_year + 1
        next_month = 1
    else:
        next_year = curr_year
        next_month = curr_month + 1
        
    periods = []
    
    month_names = {
        1: "Janeiro de",
        2: "Fevereiro de",
        3: "Março de",
        4: "Abril de",
        5: "Maio de",
        6: "Junho de",
        7: "Julho de",
        8: "Agosto de",
        9: "Setembro de",
        10: "Outubro de",
        11: "Novembro de",
        12: "Dezembro de"
    }
    
    y = start_year
    m = start_month
    while (y < next_year) or (y == next_year and m <= next_month):
        key = f"{y}-{m:02d}"
        label = f"{month_names[m]} {y}"
        periods.append((key, label))
        
        if m == 12:
            m = 1
            y += 1
        else:
            m += 1
            
    return periods

@app.route('/')
def index():
    data = load_data()
    if 'periodos' not in data or not isinstance(data['periodos'], list):
        data['periodos'] = []
    periodos = data['periodos']
    
    # Generate periods list dynamically
    period_options = generate_periods()
    
    # Default selected period is the current month
    today = datetime.date.today()
    default_period = f"{today.year}-{today.month:02d}"
    
    selected_name = request.args.get('periodo', default_period)
    
    # Find active period data
    active_period = next((p for p in periodos if p['nome'] == selected_name), None)
    
    # If not found, initialize it automatically with empty structures and save it
    if not active_period:
        active_period = {
            'nome': selected_name,
            'receitas': {},
            'contas_bancarias': {},
            'contas': {}
        }
        periodos.append(active_period)
        # Save to YAML
        with open(YAML_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            
    # Calculate stats
    receitas_dict = active_period.get('receitas', {})
    
    # Normalize and calculate recipes
    total_receitas = 0.0
    salario = 0.0
    guardado = 0.0
    
    normalized_receitas = {}
    for r_name, r_info in receitas_dict.items():
        if isinstance(r_info, dict):
            val = float(r_info.get('valor', 0.0))
            dia_pag = int(r_info.get('dia_pagamento', 5))
            dest = r_info.get('conta_destino', '')
        else:
            # old format fallback
            val = float(r_info)
            dia_pag = 5
            dest = 'Itaú'
            
        total_receitas += val
        if 'salario' in r_name.lower() or 'salário' in r_name.lower():
            salario += val
        elif 'guardado' in r_name.lower():
            guardado += val
            
        normalized_receitas[r_name] = {
            'valor': val,
            'valor_formatado': format_currency(val),
            'dia_pagamento': dia_pag,
            'conta_destino': dest
        }
    
    contas_bancarias = active_period.get('contas_bancarias', {})
    
    # Format bank accounts
    bancarias_stats = {}
    total_saldos = 0.0
    for bank_name, info in contas_bancarias.items():
        saldo = float(info.get('saldo_atual', 0.0))
        total_saldos += saldo
        
        transactions = info.get('transacoes', [])
        formatted_txs = []
        for t in transactions:
            tx_type = t.get('tipo', 'Debito') # 'Entrada' or 'Debito'
            formatted_txs.append({
                'descricao': t.get('descricao', ''),
                'valor': t.get('valor', 0.0),
                'valor_formatado': format_currency(t.get('valor', 0.0)),
                'tipo': tx_type
            })
            
        bancarias_stats[bank_name] = {
            'saldo_atual': saldo,
            'saldo_formatado': format_currency(saldo),
            'transacoes': formatted_txs,
            'count': len(transactions)
        }

    contas = active_period.get('contas', {})
    
    # Calculate totals per card/account
    contas_stats = {}
    overall_total = 0.0
    
    for bank_name, info in contas.items():
        transactions = info.get('transacoes', [])
        total_bank = sum(t.get('valor', 0.0) for t in transactions)
        overall_total += total_bank
        
        # Format individual transaction values for UI
        formatted_txs = []
        for t in transactions:
            formatted_txs.append({
                'descricao': t.get('descricao', ''),
                'valor': t.get('valor', 0.0),
                'valor_formatado': format_currency(t.get('valor', 0.0))
            })
        
        limite_total = float(info.get('limite_total', 0.0))
        dia_fechamento = int(info.get('dia_fechamento', 10))
        dia_vencimento = int(info.get('dia_vencimento', 20))
        limite_disponivel = limite_total - total_bank

        contas_stats[bank_name] = {
            'transacoes': formatted_txs,
            'total_formatado': format_currency(total_bank),
            'total': total_bank,
            'count': len(transactions),
            'limite_total': limite_total,
            'limite_total_formatado': format_currency(limite_total),
            'limite_disponivel': limite_disponivel,
            'limite_disponivel_formatado': format_currency(limite_disponivel),
            'dia_fechamento': dia_fechamento,
            'dia_vencimento': dia_vencimento
        }
        
    today = datetime.date.today()
    receitas_previstas = 0.0
    for r_name, r_data in normalized_receitas.items():
        if r_data['dia_pagamento'] >= today.day:
            receitas_previstas += r_data['valor']
            
    restante = total_saldos + receitas_previstas - overall_total
    dias_restantes = get_days_until_next_5th()
    media_diaria = restante / dias_restantes if restante > 0 else 0.0
    
    # Format stats
    stats = {
        'salario': format_currency(salario),
        'guardado': format_currency(guardado),
        'total_receitas': format_currency(total_receitas),
        'total_spent': format_currency(overall_total),
        'restante': format_currency(restante),
        'dias_restantes': dias_restantes,
        'media_diaria': format_currency(media_diaria),
        'raw_salario': salario,
        'raw_guardado': guardado,
        'raw_total_spent': overall_total,
        'raw_restante': restante,
        'raw_media_diaria': media_diaria,
        'is_negative': restante < 0
    }
    
    receitas_keys = list(normalized_receitas.keys())
    
    return render_template(
        'index.html',
        period_options=period_options,
        selected_period=selected_name,
        stats=stats,
        contas=contas_stats,
        contas_bancarias=bancarias_stats,
        receitas_keys=receitas_keys
    )

@app.route('/add-transaction', methods=['POST'])
def add_transaction():
    tipo = request.form.get('tipo')
    descricao = request.form.get('descricao')
    valor_str = request.form.get('valor', '0.0')
    periodo = request.form.get('periodo')
    
    try:
        valor = float(valor_str)
    except ValueError:
        valor = 0.0
        
    if not periodo:
        return abort(400, description="Período é obrigatório.")
        
    data = load_data()
    periodos = data.get('periodos', [])
    
    active_period = next((p for p in periodos if p['nome'] == periodo), None)
    if not active_period:
        return abort(404, description="Período não encontrado.")
        
    contas_bancarias = active_period.setdefault('contas_bancarias', {})
    contas = active_period.setdefault('contas', {})
    receitas = active_period.setdefault('receitas', {})
    
    if tipo == 'Entrada':
        conta_destino = request.form.get('conta_destino')
        dia_pagamento_str = request.form.get('dia_pagamento', '5')
        try:
            dia_pagamento = int(dia_pagamento_str)
        except ValueError:
            dia_pagamento = 5
            
        if not conta_destino:
            return abort(400, description="Conta de destino é obrigatória para Entradas.")
            
        # Case-insensitive match bank account
        matched_bank = None
        for k in contas_bancarias.keys():
            if k.lower() == conta_destino.lower():
                matched_bank = k
                break
        if not matched_bank:
            matched_bank = conta_destino
            
        bank_data = contas_bancarias.setdefault(matched_bank, {})
        bank_data['saldo_atual'] = bank_data.get('saldo_atual', 0.0) + valor
        
        # Log transaction in bank account
        bank_txs = bank_data.setdefault('transacoes', [])
        bank_txs.append({
            'descricao': descricao,
            'valor': valor,
            'tipo': 'Entrada'
        })
        
        # Save dynamically under receitas
        receita_key = descricao or 'Outra Receita'
        matched_rec = None
        for k in receitas.keys():
            if k.lower() == receita_key.lower():
                matched_rec = k
                break
        if not matched_rec:
            matched_rec = receita_key
            
        rec_data = receitas.setdefault(matched_rec, {})
        if isinstance(rec_data, dict):
            rec_data['valor'] = rec_data.get('valor', 0.0) + valor
            rec_data['dia_pagamento'] = dia_pagamento
            rec_data['conta_destino'] = matched_bank
        else:
            # Fallback if old format was a float
            receitas[matched_rec] = {
                'valor': float(rec_data) + valor,
                'dia_pagamento': dia_pagamento,
                'conta_destino': matched_bank
            }
            
    elif tipo == 'Debito':
        conta_destino = request.form.get('conta_destino')
        if not conta_destino:
            return abort(400, description="Conta bancária é obrigatória para Débito.")
            
        # Case-insensitive match
        matched_bank = None
        for k in contas_bancarias.keys():
            if k.lower() == conta_destino.lower():
                matched_bank = k
                break
        if not matched_bank:
            matched_bank = conta_destino
            
        bank_data = contas_bancarias.setdefault(matched_bank, {})
        bank_data['saldo_atual'] = bank_data.get('saldo_atual', 0.0) - valor
        
        # Log transaction in bank account
        bank_txs = bank_data.setdefault('transacoes', [])
        bank_txs.append({
            'descricao': descricao,
            'valor': valor,
            'tipo': 'Debito'
        })
        
    elif tipo == 'Credito':
        cartao_credito = request.form.get('cartao_credito')
        if not cartao_credito:
            return abort(400, description="Cartão de Crédito é obrigatório para Crédito.")
            
        # Case-insensitive match
        matched_card = None
        for k in contas.keys():
            if k.lower() == cartao_credito.lower():
                matched_card = k
                break
        if not matched_card:
            matched_card = cartao_credito
            
        card_data = contas.setdefault(matched_card, {})
        card_data.setdefault('limite_total', 0.0)
        card_data.setdefault('dia_fechamento', 10)
        card_data.setdefault('dia_vencimento', 20)
        
        card_txs = card_data.setdefault('transacoes', [])
        card_txs.append({
            'descricao': descricao,
            'valor': valor
        })
        
    # Save to yaml
    with open(YAML_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
    return redirect(url_for('index', periodo=periodo))

@app.route('/configure-card', methods=['POST'])
def configure_card():
    card_name = request.form.get('card_name')
    limite_total_str = request.form.get('limite_total', '0.0')
    dia_fechamento_str = request.form.get('dia_fechamento', '10')
    dia_vencimento_str = request.form.get('dia_vencimento', '20')
    periodo = request.form.get('periodo')
    
    try:
        limite_total = float(limite_total_str)
    except ValueError:
        limite_total = 0.0
        
    try:
        dia_fechamento = int(dia_fechamento_str)
    except ValueError:
        dia_fechamento = 10
        
    try:
        dia_vencimento = int(dia_vencimento_str)
    except ValueError:
        dia_vencimento = 20
        
    if not card_name or not periodo:
        return abort(400, description="Nome do cartão e período são obrigatórios.")
        
    data = load_data()
    periodos = data.get('periodos', [])
    
    active_period = next((p for p in periodos if p['nome'] == periodo), None)
    if not active_period:
        return abort(404, description="Período não encontrado.")
        
    contas = active_period.setdefault('contas', {})
    
    # Case-insensitive check to update or create
    matched_card = None
    for k in contas.keys():
        if k.lower() == card_name.lower():
            matched_card = k
            break
            
    if not matched_card:
        matched_card = card_name
        
    card_data = contas.setdefault(matched_card, {})
    card_data['limite_total'] = limite_total
    card_data['dia_fechamento'] = dia_fechamento
    card_data['dia_vencimento'] = dia_vencimento
    card_data.setdefault('transacoes', [])
    
    # Save to yaml
    with open(YAML_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
    return redirect(url_for('index', periodo=periodo))

@app.route('/configure-bank', methods=['POST'])
def configure_bank():
    bank_name = request.form.get('bank_name')
    saldo_atual_str = request.form.get('saldo_atual', '0.0')
    periodo = request.form.get('periodo')
    
    try:
        saldo_atual = float(saldo_atual_str)
    except ValueError:
        saldo_atual = 0.0
        
    if not bank_name or not periodo:
        return abort(400, description="Nome da conta e período são obrigatórios.")
        
    data = load_data()
    periodos = data.get('periodos', [])
    
    active_period = next((p for p in periodos if p['nome'] == periodo), None)
    if not active_period:
        return abort(404, description="Período não encontrado.")
        
    contas_bancarias = active_period.setdefault('contas_bancarias', {})
    
    # Case-insensitive search
    matched_bank = None
    for k in contas_bancarias.keys():
        if k.lower() == bank_name.lower():
            matched_bank = k
            break
            
    if not matched_bank:
        matched_bank = bank_name
        
    bank_data = contas_bancarias.setdefault(matched_bank, {})
    bank_data['saldo_atual'] = saldo_atual
    bank_data.setdefault('transacoes', [])
    
    # Save to yaml
    with open(YAML_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
    return redirect(url_for('index', periodo=periodo))

@app.route('/delete-transaction', methods=['POST'])
def delete_transaction():
    tipo = request.form.get('tipo')
    entidade = request.form.get('entidade')
    idx_str = request.form.get('index')
    periodo = request.form.get('periodo')
    
    try:
        idx = int(idx_str)
    except (ValueError, TypeError):
        return abort(400, description="Índice inválido.")
        
    if not periodo or not entidade:
        return abort(400, description="Parâmetros ausentes.")
        
    data = load_data()
    periodos = data.get('periodos', [])
    
    active_period = next((p for p in periodos if p['nome'] == periodo), None)
    if not active_period:
        return abort(404, description="Período não encontrado.")
        
    if tipo == 'Bank':
        contas_bancarias = active_period.get('contas_bancarias', {})
        if entidade in contas_bancarias:
            bank_data = contas_bancarias[entidade]
            transactions = bank_data.get('transacoes', [])
            if 0 <= idx < len(transactions):
                tx = transactions.pop(idx)
                tx_valor = float(tx.get('valor', 0.0))
                tx_tipo = tx.get('tipo', 'Debito')
                
                if tx_tipo == 'Debito':
                    # Add back to bank account
                    bank_data['saldo_atual'] = bank_data.get('saldo_atual', 0.0) + tx_valor
                elif tx_tipo == 'Entrada':
                    # Subtract from bank account
                    bank_data['saldo_atual'] = bank_data.get('saldo_atual', 0.0) - tx_valor
                    
                    # Remove or subtract from receitas
                    receitas = active_period.get('receitas', {})
                    tx_desc = tx.get('descricao', 'Outra Receita')
                    
                    matched_rec = None
                    for k in receitas.keys():
                        if k.lower() == tx_desc.lower():
                            matched_rec = k
                            break
                    if not matched_rec and tx_desc in receitas:
                        matched_rec = tx_desc
                        
                    if matched_rec:
                        rec_data = receitas[matched_rec]
                        if isinstance(rec_data, dict):
                            new_val = rec_data.get('valor', 0.0) - tx_valor
                            if new_val <= 0:
                                receitas.pop(matched_rec)
                            else:
                                rec_data['valor'] = new_val
                        else:
                            # old float format
                            new_val = float(rec_data) - tx_valor
                            if new_val <= 0:
                                receitas.pop(matched_rec)
                            else:
                                receitas[matched_rec] = new_val
                                
    elif tipo == 'Credito':
        contas = active_period.get('contas', {})
        if entidade in contas:
            card_data = contas[entidade]
            transactions = card_data.get('transacoes', [])
            if 0 <= idx < len(transactions):
                transactions.pop(idx)
                
    with open(YAML_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
    return redirect(url_for('index', periodo=periodo))

@app.route('/delete-card', methods=['POST'])
def delete_card():
    card_name = request.form.get('card_name')
    periodo = request.form.get('periodo')
    
    if not card_name or not periodo:
        return abort(400, description="Parâmetros ausentes.")
        
    data = load_data()
    periodos = data.get('periodos', [])
    
    active_period = next((p for p in periodos if p['nome'] == periodo), None)
    if not active_period:
        return abort(404, description="Período não encontrado.")
        
    contas = active_period.get('contas', {})
    
    matched_key = None
    for k in contas.keys():
        if k.lower() == card_name.lower():
            matched_key = k
            break
            
    if matched_key:
        contas.pop(matched_key)
        
    with open(YAML_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
    return redirect(url_for('index', periodo=periodo))

@app.route('/delete-bank', methods=['POST'])
def delete_bank():
    bank_name = request.form.get('bank_name')
    periodo = request.form.get('periodo')
    
    if not bank_name or not periodo:
        return abort(400, description="Parâmetros ausentes.")
        
    data = load_data()
    periodos = data.get('periodos', [])
    
    active_period = next((p for p in periodos if p['nome'] == periodo), None)
    if not active_period:
        return abort(404, description="Período não encontrado.")
        
    contas_bancarias = active_period.get('contas_bancarias', {})
    
    matched_key = None
    for k in contas_bancarias.keys():
        if k.lower() == bank_name.lower():
            matched_key = k
            break
            
    if matched_key:
        contas_bancarias.pop(matched_key)
        
    with open(YAML_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
    return redirect(url_for('index', periodo=periodo))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

