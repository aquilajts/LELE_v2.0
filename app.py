from flask import Flask, request, jsonify, render_template, render_template_string, redirect, session
from flask_cors import CORS
from datetime import datetime, timedelta
from supabase import create_client
import os

app = Flask(__name__)
CORS(app)
app.secret_key = 'sua_chave_super_secreta'

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

MASTER_IDS = ['Confiadmin', 'Acessorestrito']
GERENTE_ID = 'Acessorestrito'
SUPERVISOR_ID = 'Confiadmin'
HTML = open("templates/index.html", encoding="utf-8").read()
LOGIN_HTML = open("templates/login.html", encoding="utf-8").read()

@app.route('/')
def home():
    return render_template("home.html")

@app.route('/cliente')
def cliente():
    return render_template("cliente.html")
    
@app.route('/simulacao')
def simulacao():
    return render_template("simulacao.html")

@app.route('/coberturas')
def coberturas():
    return render_template("coberturas.html")
    
@app.route('/login', methods=['GET'])
def login_page():
    return render_template("login.html")

@app.route('/login', methods=['POST'])
def realizar_login():
    data = request.get_json()
    user_id = data.get('id')
    senha = data.get('senha')

    if not user_id or not senha or len(senha) != 5 or not senha.isdigit():
        return 'ID ou senha inválidos', 400

    try:
        # Consulta o Supabase por esse ID
        result = supabase.table("usuarios").select("*").eq("id", user_id).execute()
        usuarios = result.data

        if usuarios:
            # ID já existe: valida a senha
            if usuarios[0]["senha"] != senha:
                return 'ID ou senha inválidos', 400
        else:
            # ID não existe: cria automaticamente com senha padrão
            supabase.table("usuarios").insert({
                "id": user_id,
                "senha": "00000",
                "perfil": "usuario"
            }).execute()

            # Se a senha digitada for diferente de "00000", nega o acesso
            if senha != "00000":
                return 'ID ou senha inválidos', 400

        # Login válido
        session['usuario_id'] = user_id
        session['senha'] = senha
        return '', 200

    except Exception as e:
        print("Erro ao processar login:", e)
        return 'Erro no servidor', 500

@app.route('/id')
def obter_id():
    if 'usuario_id' not in session:
        return jsonify({'id': None, 'senha': None, 'perfil': 'usuario'})

    perfil = 'usuario'
    if session['usuario_id'] == GERENTE_ID:
        perfil = 'gerente'
    elif session['usuario_id'] == SUPERVISOR_ID:
        perfil = 'supervisor'

    return jsonify({
        'id': session['usuario_id'],
        'senha': session['senha'],
        'perfil': perfil
    })

@app.route('/painel')
def painel():
    if 'usuario_id' not in session:
        return redirect('/')
    return render_template_string(HTML)

@app.route('/alterar-senha', methods=['POST'])
def alterar_senha():
    if 'usuario_id' not in session:
        return 'Não autorizado', 403

    data = request.get_json()
    nova_senha = data.get('nova_senha')

    if not nova_senha or len(nova_senha) != 5 or not nova_senha.isdigit():
        return 'Senha inválida', 400

    session['senha'] = nova_senha
    supabase.table("usuarios").update({"senha": nova_senha}).eq("id", session['usuario_id']).execute()

    return '', 200

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
    if user_id == SUPERVISOR_ID:
        return 'Supervisores não podem cadastrar vendas', 403

    data = request.get_json()

    venda = {
        "data": (datetime.utcnow() - timedelta(hours=3)).strftime('%d/%m/%Y %H:%M'),
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
    except Exception as e:
        print("Erro ao salvar venda:", e)
        return 'Erro ao salvar', 500

    return '', 200

@app.route('/excluir', methods=['DELETE'])
def excluir():
    if 'usuario_id' not in session or session['usuario_id'] != GERENTE_ID:
        return 'Não autorizado', 403

    placa = request.args.get("placa")
    data = request.args.get("data")

    supabase.table("vendas").delete().match({"placa": placa, "data": data}).execute()
    return '', 200

@app.route('/editar', methods=['POST'])
def editar():
    if 'usuario_id' not in session or session['usuario_id'] != GERENTE_ID:
        return 'Não autorizado', 403

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

@app.route('/buscar-faixa')
def buscar_faixa():
    try:
        nome_tabela = request.args.get('tabela')  # 'tabela' ou 'tabelade'
        fipe = float(request.args.get('fipe'))
        coluna = request.args.get('coluna')

        dados = supabase.table(nome_tabela).select(f"FIPE, FIPE2, {coluna}").execute().data

        faixa = next((linha for linha in dados if linha["FIPE"] <= fipe <= linha["FIPE2"]), None)

        if not faixa:
            return jsonify({"valor": "não encontrado"})

        return jsonify({"valor": faixa[coluna]})
    except Exception as e:
        print("Erro na busca por faixa:", e)
        return jsonify({"valor": "erro"})


@app.route('/valor')
def buscar_valor():
    try:
        nome_tabela = request.args.get('tabela')  # 'tabela' ou 'tabelade'
        fipe = float(request.args.get('fipe'))
        coluna = request.args.get('coluna')

        dados = supabase.table(nome_tabela).select("*").eq("FIPE", fipe).execute().data
        if not dados:
            return jsonify({"valor": "não encontrado"})

        valor = dados[0].get(coluna)
        valor_formatado = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        return jsonify({"valor": valor_formatado})
    except Exception as e:
        print("Erro ao buscar valor:", e)
        return jsonify({"valor": "erro"})

@app.route('/contratacao')
def contratacao():
    return render_template("contratacao.html")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
