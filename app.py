import os
import datetime
import yaml
from flask import Flask, render_template, request, abort

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
    salario = active_period['receitas'].get('salario', 0.0)
    guardado = active_period['receitas'].get('guardado', 0.0)
    
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
        
    restante = (salario + guardado) - overall_total
    dias_restantes = get_days_until_next_5th()
    media_diaria = restante / dias_restantes if restante > 0 else 0.0
    
    # Format stats
    stats = {
        'salario': format_currency(salario),
        'guardado': format_currency(guardado),
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
    
    return render_template(
        'index.html',
        period_names=period_names,
        selected_period=selected_name,
        stats=stats,
        contas=contas_stats
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
