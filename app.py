from flask import Flask, request, jsonify, render_template_string, redirect, session
from flask_cors import CORS
from datetime import datetime
from supabase import create_client
import os

app = Flask(__name__)
CORS(app)
app.secret_key = 'sua_chave_super_secreta'

# Pegando chaves do ambiente (Render)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

MASTER_IDS = ['Confiadmin', 'Acessorestrito']
HTML = open("templates/index.html", encoding="utf-8").read()


@app.route('/')
def login():
    return render_template_string(open("templates/login.html", encoding="utf-8").read())


@app.route('/login', methods=['POST'])
def realizar_login():
    data = request.get_json()
    user_id = data.get('id')
    if user_id and 5 <= len(user_id) <= 20:
        session['usuario_id'] = user_id
        return '', 200
    return 'ID inválido', 400


@app.route('/id')
def obter_id():
    if 'usuario_id' not in session:
        return jsonify({'id': None, 'isMaster': False})
    return jsonify({
        'id': session['usuario_id'],
        'isMaster': session['usuario_id'] in MASTER_IDS
    })


@app.route('/painel')
def painel():
    if 'usuario_id' not in session:
        return redirect('/')
    return render_template_string(HTML)


@app.route('/vendas')
def listar_vendas():
    if 'usuario_id' not in session:
        return jsonify([])

    usuario_id = session['usuario_id']
    if usuario_id in MASTER_IDS:
        res = supabase.table("vendas").select("*").order("data", desc=True).execute()
    else:
        res = supabase.table("vendas").select("*").eq("usuario_id", usuario_id).order("data", desc=True).execute()

    return jsonify(res.data)


@app.route('/salvar', methods=['POST'])
def salvar():
    if 'usuario_id' not in session:
        return 'Não autorizado', 403
    user_id = session['usuario_id']
    if user_id in MASTER_IDS:
        return 'Contas Master não podem cadastrar vendas', 403

    data = request.get_json()

    venda = {
        "data": datetime.now().strftime('%d/%m/%Y %H:%M'),
        "cliente": data.get("cliente"),
        "telefone": data.get("telefone"),
        "veiculo": data.get("veiculo"),
        "placa": data.get("placa"),
        "fipe": data.get("fipe"),
        "mensalidade_original": data.get("mensalidade_original"),
        "mensalidade_desconto": data.get("mensalidade_desconto"),
        "participacao": data.get("participacao"),
        "descTexto": data.get("descTexto"),
        "obs": data.get("obs"),
        "usuario_id": user_id
    }

    try:
        supabase.table("vendas").insert(venda).execute()
        return '', 200
    except Exception as e:
        print("Erro ao salvar venda:", e)
        return 'Erro ao salvar', 500

@app.route('/excluir', methods=['DELETE'])
def excluir():
    if 'usuario_id' not in session:
        return 'Não autorizado', 403
    if session['usuario_id'] in MASTER_IDS:
        return 'Contas Master não podem excluir', 403

    placa = request.args.get("placa")
    data = request.args.get("data")

    supabase.table("vendas").delete().match({"placa": placa, "data": data}).execute()
    return '', 200


@app.route('/editar', methods=['POST'])
def editar():
    if 'usuario_id' not in session:
        return 'Não autorizado', 403
    if session['usuario_id'] in MASTER_IDS:
        return 'Contas Master não podem editar', 403

    data = request.get_json()
    venda_id = data.get('id')

    campos = {
        'cliente': data.get('cliente'),
        'telefone': data.get('telefone'),
        'veiculo': data.get('veiculo'),
        'placa': data.get('placa'),
        'fipe': data.get('fipe'),
        'mensalidade_original': data.get('mensalidade_original'),
        'mensalidade_desconto': data.get('mensalidade_desconto'),
        'participacao': data.get('participacao'),
        'descTexto': data.get('descTexto'),
        'obs': data.get('obs')
    }

    supabase.table("vendas").update(campos).eq("id", venda_id).execute()
    return '', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
