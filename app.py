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

@app.route('/')
def index():
    data = load_data()
    periodos = data.get('periodos', [])
    if not periodos:
        return "Nenhum dado financeiro encontrado no arquivo modelo.yaml. Certifique-se de preenchê-lo.", 404
    
    # Get period names
    period_names = [p['nome'] for p in periodos]
    
    # Selected period (defaults to the first one)
    selected_name = request.args.get('periodo', period_names[0])
    
    # Find active period data
    active_period = next((p for p in periodos if p['nome'] == selected_name), None)
    if not active_period:
        return abort(404, description="Período não encontrado.")
    
    # Calculate stats
    receitas_dict = active_period.get('receitas', {})
    salario = receitas_dict.get('salario', 0.0)
    guardado = receitas_dict.get('guardado', 0.0)
    
    # Calculate dynamic total income
    total_receitas = sum(val for val in receitas_dict.values() if isinstance(val, (int, float)))
    
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
        
        contas_stats[bank_name] = {
            'transacoes': formatted_txs,
            'total_formatado': format_currency(total_bank),
            'total': total_bank,
            'count': len(transactions)
        }
        
    restante = total_receitas - overall_total
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
    
    receitas_keys = list(receitas_dict.keys())
    
    return render_template(
        'index.html',
        period_names=period_names,
        selected_period=selected_name,
        stats=stats,
        contas=contas_stats,
        receitas_keys=receitas_keys
    )

@app.route('/add-transaction', methods=['POST'])
def add_transaction():
    tipo = request.form.get('tipo')
    descricao = request.form.get('descricao')
    valor_str = request.form.get('valor', '0.0')
    categoria = request.form.get('categoria')
    periodo = request.form.get('periodo')
    
    try:
        valor = float(valor_str)
    except ValueError:
        valor = 0.0
        
    if not categoria or not periodo:
        return abort(400, description="Categoria/Cartão e Período são campos obrigatórios.")
        
    data = load_data()
    periodos = data.get('periodos', [])
    
    active_period = next((p for p in periodos if p['nome'] == periodo), None)
    if not active_period:
        return abort(404, description="Período não encontrado.")
        
    if tipo == 'Entrada':
        receitas = active_period.setdefault('receitas', {})
        # Find case-insensitive match or create new key
        matched_key = None
        for k in receitas.keys():
            if k.lower() == categoria.lower():
                matched_key = k
                break
        if not matched_key:
            matched_key = categoria
            
        receitas[matched_key] = receitas.get(matched_key, 0.0) + valor
        
    elif tipo == 'Despesa':
        contas = active_period.setdefault('contas', {})
        # Find case-insensitive match or create new card
        matched_card = None
        for k in contas.keys():
            if k.lower() == categoria.lower():
                matched_card = k
                break
        if not matched_card:
            matched_card = categoria
            
        card_data = contas.setdefault(matched_card, {})
        transactions = card_data.setdefault('transacoes', [])
        
        transactions.append({
            'descricao': descricao,
            'valor': valor
        })
        
    # Save to yaml
    with open(YAML_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
    return redirect(url_for('index', periodo=periodo))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
