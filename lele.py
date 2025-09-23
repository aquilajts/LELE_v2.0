from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from supabase import create_client, Client
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pytz
import logging
import json
from zoneinfo import ZoneInfo

# Configuração de logging
logging.basicConfig(level=logging.DEBUG)

# Carrega variáveis de ambiente
load_dotenv()

# Inicializa o Flask
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'churrasquinho_lele_v2_fixed_key_2025')  # Adicione SECRET_KEY no Render env pra segurança

# Configura o Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/index', methods=['GET'])
def index():
    logging.debug(f"Session check in /index: {session.get('autenticado_cliente')}")
    if not session.get('autenticado_cliente'):
        return redirect(url_for('login'))
    # Checa tempo de sessão
    last_access = session.get('last_access')
    if last_access:
        if datetime.now(ZoneInfo("America/Sao_Paulo")) - last_access > timedelta(minutes=180):
            session.clear()
            return redirect(url_for('login'))
    session['last_access'] = datetime.now(ZoneInfo("America/Sao_Paulo"))
    return render_template('index.html', session_script="sessionStorage.setItem('autenticado_cliente', 'true');")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nome_input = request.form.get('nome').strip()
        senha = request.form.get('senha')
        if len(senha) < 6:
            return render_template('login.html', erro="Senha deve ter pelo menos 6 dígitos", authenticated=False)
        
        nome_lower = nome_input.lower()
        check_nome = supabase.table('clientes').select('id_cliente, senha, nome, aniversario').eq('nome_lower', nome_lower).execute()
        
        if check_nome.data:
            existing = check_nome.data[0]
            if existing['senha'] == senha:
                session['autenticado_cliente'] = True
                session['id_cliente'] = existing['id_cliente']
                session.permanent = True
                app.permanent_session_lifetime = timedelta(minutes=180)

                # 🔎 Aqui entra a checagem do aniversário
                if not existing.get('aniversario'):
                    return render_template('login.html', solicitar_aniversario=True)

                return redirect(url_for('index'))
            else:
                return render_template('login.html', erro="Senha incorreta. O nome já está cadastrado, tente outra senha ou nome.", authenticated=False)
        else:
            # cadastro novo
            id_cliente = f"{nome_lower}_{senha}"
            new_client = {
                'nome': nome_input,
                'nome_lower': nome_lower,
                'senha': senha,
                'id_cliente': id_cliente
            }
            try:
                result = supabase.table('clientes').insert(new_client).execute()
                if result.data:
                    session['autenticado_cliente'] = True
                    session['id_cliente'] = id_cliente
                    session.permanent = True
                    app.permanent_session_lifetime = timedelta(minutes=180)
                    
                    # 🔎 novo cliente sempre terá aniversario vazio → já pede
                    return render_template('login.html', solicitar_aniversario=True)
                else:
                    return render_template('login.html', erro="Erro ao cadastrar", authenticated=False)
            except Exception as e:
                logging.error(f"Erro ao cadastrar cliente: {str(e)}")
                return render_template('login.html', erro="Erro ao cadastrar: Nome já pode estar em uso", authenticated=False)
    return render_template('login.html', authenticated=False)

@app.route('/atualizar_aniversario', methods=['POST'])
def atualizar_aniversario():
    if not session.get('id_cliente'):
        return jsonify({"error": "Não autenticado"}), 401
    aniversario = request.form.get('aniversario')
    if not aniversario:
        return jsonify({"error": "Data obrigatória"}), 400
    id_cliente = session['id_cliente']
    supabase.table('clientes').update({'aniversario': aniversario}).eq('id_cliente', id_cliente).execute()
    return redirect(url_for('index'))


@app.route('/esqueci_senha', methods=['POST'])
def esqueci_senha():
    nome = request.form.get('nome').strip().lower()
    aniversario = request.form.get('aniversario')
    nova_senha = request.form.get('nova_senha')

    if not nome or not aniversario:
        return render_template('login.html', erro="Preencha todos os campos", authenticated=False)

    query = supabase.table('clientes').select('id_cliente, aniversario').eq('nome_lower', nome).execute()
    if not query.data:
        return render_template('login.html', erro="Usuário não encontrado", authenticated=False)

    cliente = query.data[0]
    if cliente.get('aniversario') != aniversario:
        return render_template('login.html', erro="Data de aniversário incorreta", authenticated=False)

    # Se já veio a nova senha → redefinir
    if nova_senha:
        if len(nova_senha) < 6:
            return render_template('login.html', erro="Senha deve ter ao menos 6 dígitos", authenticated=False)

        supabase.table('clientes').update({'senha': nova_senha}).eq('id_cliente', cliente['id_cliente']).execute()

        # 🔑 Redireciona para /login com mensagem de sucesso
        return redirect(url_for('login', msg="Senha redefinida com sucesso!"))

    # Se ainda não veio a nova senha → renderiza o login pedindo a senha
    return render_template('login.html', reset_senha=True, nome=nome, aniversario=aniversario)



# Rota para o cardápio
@app.route('/cardapio', methods=['GET'])
def cardapio():
    mesa = request.args.get('mesa', default='1', type=str)
    response = supabase.table('itens').select('*').execute()
    itens = response.data
    categorias = {}
    for item in itens:
        categoria = item['categoria']
        if categoria not in categorias:
            categorias[categoria] = []
        item['imagem_url'] = item.get('imagem_url', '/static/produtos/default.png')
        categorias[categoria].append(item)
    return render_template('cardapio.html', categorias=categorias, mesa=mesa)

@app.route('/enviar_pedido', methods=['POST'])
def enviar_pedido():
    try:
        if not session.get('autenticado_cliente'):
            return jsonify({"error": "Usuário não logado, faça login primeiro"}), 401

        data = request.json
        mesa = data.get('mesa')
        contato = data.get('contato')
        observacoes = data.get('observacoes', '')
        itens = data.get('produto')
        total = data.get('total', 0)

        if not all([mesa, contato, itens]) or len(itens) == 0:
            return jsonify({"error": "Mesa, contato e itens são obrigatórios"}), 400

        nomes_produtos = []
        for item in itens:
            item_id = item['id']
            quantidade = item['quantidade']
            response_item = supabase.table('itens').select('nome, preco').eq('ID', item_id).execute()
            if not response_item.data:
                logging.warning(f"Item {item_id} não encontrado no Supabase")
                return jsonify({"error": f"Item {item_id} não encontrado"}), 404
        
            item_data = response_item.data[0]
            nome_produto = item_data['nome']
            preco_unit = item_data['preco']
            sabor = item.get('sabor', '')
            display_nome = f"{nome_produto} ({sabor}) - R$ {preco_unit}" if sabor else f"{nome_produto} - R$ {preco_unit}"
            nomes_produtos.append(display_nome)
        
        # Recalcula total se necessário
        if total == 0:
            total = sum(item_data['preco'] * quantidade for item in itens for item_data in supabase.table('itens').select('preco').eq('ID', item['id']).execute().data)

        # Buscar nome do cliente logado
        id_cliente = session.get('id_cliente')
        response_cliente = supabase.table('clientes').select('nome').eq('id_cliente', id_cliente).execute()
        nome_cliente = response_cliente.data[0]['nome'] if response_cliente.data else 'Cliente Desconhecido'
        
        pedido = {
            'mesa': mesa,
            'nome': nome_cliente,  # Preenchido com nome do cliente
            'contato': contato,
            'produto': nomes_produtos,
            'total': total,
            'status': 'Pedido Realizado',
            'descricao': observacoes,
            'data_hora': datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(),
            'id_cliente': id_cliente
        }
        response_insert = supabase.table('pedidos_finalizados').insert(pedido).execute()

        if not response_insert.data:
            logging.error(f"Erro no insert Supabase: {response_insert.text}")
            return jsonify({"error": "Falha ao inserir pedido", "detalhe": response_insert.text}), 500

        return jsonify({
            "message": "Pedido enviado com sucesso",
            "pedido_id": response_insert.data[0]['pedido_numero']
        }), 201

    except Exception as e:
        logging.error(f"Erro ao enviar pedido: {str(e)}")
        return jsonify({"error": "Erro interno no servidor", "detalhe": str(e)}), 500

# Rota para o painel de pedidos (somente finalizados)
@app.route('/pedidos', methods=['GET'])
def pedidos():
    try:
        response = supabase.table('pedidos_finalizados').select('*').order('pedido_numero', desc=True).execute()
        pedidos = response.data or []

        # Desserializa a lista de produtos
        for p in pedidos:
            if isinstance(p.get('produto'), str):
                p['produto'] = json.loads(p['produto'])
        
        return render_template('pedidos.html', pedidos=pedidos)
    except Exception as e:
        logging.error(f"Erro ao carregar pedidos: {str(e)}")
        return render_template('pedidos.html', pedidos=[]), 500
        
# Rota para informações
@app.route('/informacoes', methods=['GET'])
def informacoes():
    return render_template('informacoes.html')

@app.route('/caixa', methods=['GET'])
def caixa():
    return render_template('caixa.html')

@app.route('/caixa/minhacomanda', methods=['GET'])
def caixa_minhacomanda():
    if not session.get('autenticado_cliente'):
        return redirect(url_for('login'))
    id_cliente = session.get('id_cliente')
    response = supabase.table('pedidos_finalizados').select('*').eq('id_cliente', id_cliente).order('data_hora', desc=True).execute()
    pedidos = response.data or []
    total_gasto = sum(p['total'] for p in pedidos)
    num_pedidos = len(pedidos)
    return render_template('minhacomanda.html', pedidos=pedidos, total_gasto=total_gasto, num_pedidos=num_pedidos)

@app.route('/caixa/funcionario', methods=['GET', 'POST'])
def caixa_funcionario():
    if request.method == 'POST':
        senha = request.form.get('senha')
        if senha == 'cecilele25':  # Senha fixa
            session['autenticado_funcionario'] = True
            return redirect(url_for('caixa_funcionario'))
        else:
            return render_template('funcionario.html', erro="Senha incorreta", autenticado=False)
    autenticado = session.get('autenticado_funcionario', False)
    return render_template('funcionario.html', erro=None, autenticado=autenticado)

@app.route('/caixa/funcionario/recebimento', methods=['GET'])
def caixa_recebimento():
    if not session.get('autenticado_funcionario'):
        return redirect(url_for('caixa_funcionario'))
    
    response = supabase.table('pedidos_finalizados').select('*').order('data_hora', desc=True).execute()
    pedidos = response.data or []
    
    # Agrupar por id_cliente, filtrando apenas pedidos não pagos
    grupos = {}
    for p in pedidos:
        if p.get('status') != 'Pago':
            id_c = p['id_cliente']
            if id_c not in grupos:
                grupos[id_c] = {'pedidos': [], 'total': 0}
            
            grupos[id_c]['pedidos'].append(p)
            grupos[id_c]['total'] += p.get('total', 0) - (p.get('desconto', 0) or 0) - (p.get('dividir1', 0) or 0) - (p.get('dividir2', 0) or 0)
    
    return render_template('recebimento.html', grupos=grupos.items())

@app.route('/caixa/funcionario/aplicar_desconto', methods=['POST'])
def aplicar_desconto():
    try:
        if not session.get('autenticado_funcionario'):
            return jsonify({"error": "Funcionário não autenticado"}), 401
        
        data = request.get_json()
        pedido_numero = data.get('pedido_numero')
        desconto = data.get('desconto')
        
        if not pedido_numero or not desconto or desconto <= 0:
            return jsonify({"error": "Número do pedido e desconto válido são obrigatórios"}), 400
        
        # Atualiza o pedido específico com o desconto
        response = supabase.table('pedidos_finalizados').update({
            'desconto': desconto
        }).eq('pedido_numero', pedido_numero).execute()
        
        if response.data:
            logging.info(f"Desconto de R$ {desconto} aplicado para pedido {pedido_numero}")
            return jsonify({"message": "Desconto aplicado com sucesso"}), 200
        else:
            return jsonify({"error": "Pedido não encontrado"}), 404
            
    except Exception as e:
        logging.error(f"Erro ao aplicar desconto: {str(e)}")
        return jsonify({"error": "Erro interno do servidor"}), 500

@app.route('/caixa/funcionario/pagar_parcial', methods=['POST'])
def pagar_parcial():
    try:
        if not session.get('autenticado_funcionario'):
            return jsonify({"error": "Funcionário não autenticado"}), 401
        
        data = request.get_json()
        pedido_numero = data.get('pedido_numero')
        valor = data.get('valor')
        
        if not pedido_numero or not valor or valor <= 0:
            return jsonify({"error": "Número do pedido e valor válido são obrigatórios"}), 400
        
        # Busca o pedido atual para verificar colunas dividir
        response = supabase.table('pedidos_finalizados').select('dividir1, dividir2').eq('pedido_numero', pedido_numero).execute()
        if not response.data:
            return jsonify({"error": "Pedido não encontrado"}), 404
        
        pedido = response.data[0]
        update_data = {}
        
        if not pedido.get('dividir1'):
            update_data['dividir1'] = valor
        elif not pedido.get('dividir2'):
            update_data['dividir2'] = valor
        else:
            return jsonify({"error": "Limite de pagamentos parciais atingido (2)"}), 400
        
        # Atualiza o pedido específico
        supabase.table('pedidos_finalizados').update(update_data).eq('pedido_numero', pedido_numero).execute()
        
        logging.info(f"Pagamento parcial de R$ {valor} registrado para pedido {pedido_numero}")
        return jsonify({"message": "Pagamento parcial registrado com sucesso"}), 200
        
    except Exception as e:
        logging.error(f"Erro ao registrar pagamento parcial: {str(e)}")
        return jsonify({"error": "Erro interno do servidor"}), 500

@app.route('/caixa/funcionario/pagar_comanda', methods=['POST'])
def pagar_comanda():
    if not session.get('autenticado_funcionario'):
        return jsonify({"error": "Funcionário não autenticado"}), 401

    data = request.json
    id_cliente = data.get('id_cliente')
    
    try:
        # Verifica se id_cliente foi fornecido
        if not id_cliente:
            return jsonify({"error": "ID do cliente é obrigatório"}), 400

        # Atualiza o status para 'Pago' na tabela pedidos_finalizados
        update_response = supabase.table('pedidos_finalizados').update({'status': 'Pago'}).eq('id_cliente', id_cliente).execute()
        if not update_response.data:
            return jsonify({"error": "Nenhum pedido encontrado para atualizar"}), 404

        # Busca os pedidos pagos para extrair os produtos
        pedidos_response = supabase.table('pedidos_finalizados').select('produto', 'data_hora').eq('id_cliente', id_cliente).eq('status', 'Pago').execute()
        pedidos = pedidos_response.data or []

        # Processa cada pedido e insere na tabela vendas
        for pedido in pedidos:
            produtos = pedido.get('produto', [])
            if isinstance(produtos, str):  # Garante que é uma string JSONB
                import json
                try:
                    produtos = json.loads(produtos.replace("'", '"'))  # Converte string JSONB para lista
                except json.JSONDecodeError as e:
                    logging.error(f"Erro ao decodificar JSON para pedido {pedido.get('pedido_numero')}: {str(e)}")
                    continue
            data_hora = pedido.get('data_hora')
        
            for item in produtos:
                if isinstance(item, str):
                    parts = item.split(' - R$ ')
                    if len(parts) == 2:
                        nome = parts[0]
                        try:
                            preco = float(parts[1].replace(',', '.'))
                            # Busca a categoria na tabela itens com base no nome do produto
                            categoria_response = supabase.table('itens').select('categoria').eq('nome', nome).execute()
                            categoria = categoria_response.data[0]['categoria'] if categoria_response.data and len(categoria_response.data) > 0 else 'Não especificada'
                            insert_response = supabase.table('vendas').insert({
                                'nome': nome,
                                'categoria': categoria,
                                'preco': preco,
                                'data_hora': data_hora
                            }).execute()
                            if not insert_response.data:
                                logging.warning(f"Falha ao inserir item {nome} na tabela vendas")
                            else:
                                logging.info(f"Item {nome} inserido com categoria {categoria}")
                        except ValueError as e:
                            logging.error(f"Erro ao converter preço para float: {str(e)} para item {item}")
                            continue
                        except Exception as e:
                            logging.error(f"Erro ao buscar categoria para {nome}: {str(e)}")
                            categoria = 'Não especificada'  # Fallback em caso de erro na busca
                            insert_response = supabase.table('vendas').insert({
                                'nome': nome,
                                'categoria': categoria,
                                'preco': preco,
                                'data_hora': data_hora
                            }).execute()
                            if not insert_response.data:
                                logging.warning(f"Falha ao inserir item {nome} na tabela vendas")

        return jsonify({"message": "Comanda paga com sucesso"}), 200
    except Exception as e:
        logging.error(f"Erro ao pagar comanda: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/caixa/funcionario/estoque', methods=['GET'])
def estoque():
    """Rota para exibir a página de gerenciamento de estoque"""
    # Verifica se o funcionário está autenticado
    if not session.get('autenticado_funcionario'):
        return redirect(url_for('caixa_funcionario'))
    
    try:
        # Carrega todos os itens da tabela 'itens' (mesma tabela do cardápio)
        response = supabase.table('itens').select('*').execute()
        itens = response.data or []
        
        # Organiza por categoria (mantendo compatibilidade com o cardápio)
        categorias = {}
        for item in itens:
            categoria = item.get('categoria', 'Sem Categoria')
            if categoria not in categorias:
                categorias[categoria] = []
            
            # Formata o item para o template
            categorias[categoria].append({
                'ID': item['ID'],  # Mantém o campo ID existente
                'nome': item['nome'],
                'descricao': item.get('descricao', ''),
                'preco': float(item['preco']),
                'imagem_url': item.get('imagem_url', '/static/produtos/default.png'),
                'disponivel': item.get('disponivel', True)  # Se não existir, assume True
            })
        
        # Obter categorias únicas para o pop-up
        categorias_response = supabase.table('itens').select('categoria').execute()
        categorias_pop_up = sorted(set(c['categoria'] for c in categorias_response.data if c.get('categoria')))
        
        logging.info(f"Carregando estoque com {len(itens)} itens em {len(categorias)} categorias")
        return render_template('estoque.html', categorias=categorias, categorias_pop_up=categorias_pop_up)
    
    except Exception as e:
        logging.error(f"Erro ao carregar estoque: {str(e)}")
        # Em caso de erro, redireciona para funcionario com mensagem
        return redirect(url_for('caixa_funcionario'))

@app.route('/estoque/update', methods=['POST'])
def update_estoque():
    """Rota para atualizar a disponibilidade de um item"""
    try:
        if not session.get('autenticado_funcionario'):
            return jsonify({"error": "Funcionário não autenticado"}), 401
        
        data = request.get_json()
        item_id = data.get('id')
        disponivel = data.get('disponivel', False)
        
        if not item_id:
            return jsonify({"error": "ID do item é obrigatório"}), 400
        
        # Atualiza a coluna 'disponivel' na tabela 'itens'
        response = supabase.table('itens').update({'disponivel': disponivel}).eq('ID', item_id).execute()
        
        if response.data:
            logging.info(f"Item {item_id} atualizado para disponivel={disponivel}")
            return jsonify({"success": True, "message": "Disponibilidade atualizada"}), 200
        else:
            logging.warning(f"Nenhum item atualizado para ID {item_id}")
            return jsonify({"error": "Item não encontrado"}), 404
            
    except Exception as e:
        logging.error(f"Erro ao atualizar estoque: {str(e)}")
        return jsonify({"error": "Erro interno do servidor", "detalhe": str(e)}), 500

@app.route('/estoque/adicionar', methods=['POST'])
def estoque_adicionar():
    """Rota para adicionar um novo produto ao estoque"""
    try:
        if not session.get('autenticado_funcionario'):
            return jsonify({"error": "Funcionário não autenticado"}), 401
        
        data = request.get_json()
        nome = data.get('nome')
        descricao = data.get('descricao')
        preco = float(data.get('preco'))
        disponivel = data.get('disponivel')
        categoria = data.get('categoria')

        if not all([nome, descricao, preco, categoria]):
            return jsonify({"error": "Todos os campos são obrigatórios"}), 400

        # Gerar ID a partir do nome (sem espaços)
        id_value = nome.replace(" ", "")
        
        # Verificar se ID já existe
        check_response = supabase.table('itens').select('ID').eq('ID', id_value).execute()
        if check_response.data:
            return jsonify({"success": False, "error": "ID já existe"}), 400

        # Inserir novo item
        new_item = {
            'ID': id_value,
            'nome': nome,
            'descricao': descricao,
            'preco': preco,
            'disponivel': disponivel,
            'categoria': categoria
        }
        response = supabase.table('itens').insert(new_item).execute()
        if response.data:
            logging.info(f"Produto {nome} adicionado com ID {id_value}")
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Erro ao adicionar item"}), 500
    except Exception as e:
        logging.error(f"Erro ao adicionar produto: {str(e)}")
        return jsonify({"error": "Erro interno do servidor", "detalhe": str(e)}), 500

@app.route('/estoque/excluir', methods=['POST'])
def estoque_excluir():
    """Rota para excluir um produto do estoque"""
    try:
        if not session.get('autenticado_funcionario'):
            return jsonify({"error": "Funcionário não autenticado"}), 401
        
        data = request.get_json()
        item_id = data.get('id')
        senha = data.get('senha')

        if not item_id:
            return jsonify({"error": "ID do item é obrigatório"}), 400
        
        if senha != 'cecilele25':
            return jsonify({"success": False, "error": "Senha incorreta"}), 403

        # Excluir o item
        response = supabase.table('itens').delete().eq('ID', item_id).execute()
        if response.data:
            logging.info(f"Item {item_id} excluído com sucesso")
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Item não encontrado"}), 404
    except Exception as e:
        logging.error(f"Erro ao excluir produto: {str(e)}")
        return jsonify({"error": "Erro interno do servidor", "detalhe": str(e)}), 500

@app.route('/caixa/funcionario/relatoriofinanceiro', methods=['GET'])
def caixa_relatoriofinanceiro():
    if not session.get('autenticado_funcionario'):
        return redirect(url_for('caixa_funcionario'))

    try:
        # --- filtros vindos da URL ---
        nome = request.args.get('nome', '').strip()
        status = request.args.get('status', '').strip()
        data_inicio = request.args.get('data_inicio', '')
        data_fim = request.args.get('data_fim', '')

        query = supabase.table('pedidos_finalizados').select('*')

        # filtro por status
        if status:
            query = query.eq('status', status)

        # busca por nome
        if nome:
            query = query.ilike('nome', f"%{nome}%")

        # busca por intervalo de datas
        if data_inicio and data_fim:
            query = query.gte('data_hora', f"{data_inicio} 00:00:00").lte('data_hora', f"{data_fim} 23:59:59")
        elif data_inicio:
            query = query.gte('data_hora', f"{data_inicio} 00:00:00")
        elif data_fim:
            query = query.lte('data_hora', f"{data_fim} 23:59:59")

        # executa
        response = query.order('data_hora', desc=True).execute()
        pedidos = response.data or []

        # ajusta fuso horário para São Paulo
        tz = pytz.timezone("America/Sao_Paulo")
        for p in pedidos:
            if p.get("data_hora"):
                try:
                    dt = datetime.fromisoformat(p["data_hora"].replace("Z", "+00:00"))
                    p["data_hora"] = dt.astimezone(tz).strftime("%d/%m/%Y %H:%M:%S")
                except:
                    pass

        # métricas ajustadas
        total_vendido = sum(p.get('total', 0) for p in pedidos)
        total_pedidos = len(pedidos)
        pedidos_pagos = len([p for p in pedidos if p.get('status') == 'Pago'])
        pedidos_abertos = total_pedidos - pedidos_pagos

        return render_template(
            'relatoriofinanceiro.html',
            pedidos=pedidos,
            total_vendido=total_vendido,
            total_pedidos=total_pedidos,
            pedidos_pagos=pedidos_pagos,
            pedidos_abertos=pedidos_abertos,
            nome_filtro=nome,
            status_filtro=status,
            data_inicio=data_inicio,
            data_fim=data_fim
        )
    except Exception as e:
        logging.error(f"Erro ao carregar relatório: {str(e)}")
        return render_template('relatoriofinanceiro.html', pedidos=[], total_vendido=0, total_pedidos=0, pedidos_pagos=0, pedidos_abertos=0)

@app.route('/caixa/funcionario/relatoriodevendas', methods=['GET'])
def caixa_relatoriodevendas():
    if not session.get('autenticado_funcionario'):
        return redirect(url_for('caixa_funcionario'))

    try:
        # --- Filtros vindos da URL ---
        nome = request.args.get('nome', '').strip()
        data_inicio = request.args.get('data_inicio', '')
        data_fim = request.args.get('data_fim', '')
        categoria_filtro = request.args.get('categoria', '')

        # Obter categorias únicas da tabela vendas
        categorias_response = supabase.table('vendas').select('categoria').execute()
        categorias_set = set()
        if categorias_response.data:
            for c in categorias_response.data:
                if c.get('categoria'):  # Verifica se a categoria existe e não é nula
                    categorias_set.add(c['categoria'])
        categorias = sorted(list(categorias_set))  # Converte para lista ordenada

        # Construção da query para a tabela vendas
        query = supabase.table('vendas').select('*')

        # Filtro por nome do produto
        if nome:
            query = query.ilike('nome', f"%{nome}%")

        # Filtro por intervalo de datas
        if data_inicio and data_fim:
            query = query.gte('data_hora', f"{data_inicio} 00:00:00").lte('data_hora', f"{data_fim} 23:59:59")
        elif data_inicio:
            query = query.gte('data_hora', f"{data_inicio} 00:00:00")
        elif data_fim:
            query = query.lte('data_hora', f"{data_fim} 23:59:59")

        # Filtro por categoria (aplicado se não for vazio, ignorando "Todas")
        if categoria_filtro and categoria_filtro != '':
            query = query.eq('categoria', categoria_filtro)

        # Executa a query com ordenação por data_hora descendente
        response = query.order('data_hora', desc=True).execute()
        vendas_raw = response.data or []

        # Unifica itens por nome
        vendas_unificadas = {}
        for v in vendas_raw:
            nome_produto = v['nome']
            if nome_produto not in vendas_unificadas:
                vendas_unificadas[nome_produto] = {
                    'nome': nome_produto,
                    'categoria': v.get('categoria', 'Não especificada'),
                    'preco': v['preco'],
                    'quantidade': 0,
                    'valor_total': 0.0
                }
            vendas_unificadas[nome_produto]['quantidade'] += 1
            vendas_unificadas[nome_produto]['valor_total'] += v['preco']

        vendas = list(vendas_unificadas.values())

        # Métricas ajustadas
        total_vendido = sum(v['valor_total'] for v in vendas)
        total_itens = sum(v['quantidade'] for v in vendas)

        return render_template(
            'relatoriodevendas.html',
            vendas=vendas,
            nome_filtro=nome,
            data_inicio=data_inicio,
            data_fim=data_fim,
            categoria_filtro=categoria_filtro,
            categorias=categorias,
            total_vendido=total_vendido,
            total_itens=total_itens
        )
    except Exception as e:
        logging.error(f"Erro ao carregar relatório de vendas: {str(e)}")
        return render_template('relatoriodevendas.html', vendas=[], total_vendido=0, total_itens=0, nome_filtro='', data_inicio='', data_fim='', categoria_filtro='', categorias=[])

@app.route('/pedidos/meuspedidos', methods=['GET'])
def meus_pedidos():
    if not session.get('autenticado_cliente'):
        return redirect(url_for('login'))
    id_cliente = session.get('id_cliente')
    response = supabase.table('pedidos_finalizados').select('*').eq('id_cliente', id_cliente).execute()
    pedidos = response.data or []
    return render_template('pedidos/meuspedidos.html', pedidos=pedidos)

# rota para pedidos/lele
@app.route('/pedidos/lele', methods=['GET', 'POST'])
def pedidos_lele():
    logging.debug(f"Request method: {request.method}, Session: {session.get('autenticado_lele')}")
    if request.method == 'POST':
        senha = request.form.get('senha')
        if senha == 'cecilele25': 
            session['autenticado_lele'] = True
            session.permanent = True  # Marca session como permanente
            app.permanent_session_lifetime = timedelta(minutes=600)  # Session válida por 10 horas
            return redirect(url_for('pedidos_lele'))
        return render_template('pedidos/lele.html', erro="Senha incorreta", pedidos=[], authenticated=False)
    elif session.get('autenticado_lele') is True:
        response = supabase.table('pedidos_finalizados').select('*').order('pedido_numero', desc=True).execute()
        logging.debug(f"Response data: {response.data}")
        pedidos = response.data or []
        for p in pedidos:
            if p.get('produto') is None:
                p['produto'] = []
            elif isinstance(p.get('produto'), str):
                try:
                    p['produto'] = json.loads(p['produto'])
                except json.JSONDecodeError:
                    p['produto'] = []
            # Já array, mantém
        logging.info(f"Carregando {len(pedidos)} pedidos pra template")
        return render_template('pedidos/lele.html', pedidos=pedidos, authenticated=True)
    return render_template('pedidos/lele.html', pedidos=[], authenticated=False)
    
# rota para atualização de status
@app.route('/update_status/<int:pedido_numero>', methods=['POST'])
def update_status(pedido_numero):
    data = request.get_json()
    new_status = data.get('status')
    valid_statuses = ['Em Preparo', 'Preparado', 'Entregue']
    if new_status in valid_statuses:
        supabase.table('pedidos_finalizados').update({'status': new_status}).eq('pedido_numero', pedido_numero).execute()
        return '', 200
    return '', 400
    
# rota para apagar pedidos
@app.route('/delete_pedido/<int:pedido_numero>', methods=['DELETE'])
def delete_pedido(pedido_numero):
    response = supabase.table('pedidos_finalizados').delete().eq('pedido_numero', pedido_numero).execute()
    if response.data:
        logging.info(f"Pedido {pedido_numero} excluído")
        return jsonify({"message": "Pedido excluído"}), 200
    return jsonify({"error": "Falha ao excluir", "detalhe": str(response.error)}), 500

# Nova rota para adicionar observação
@app.route('/add_observacao/<int:pedido_numero>', methods=['POST'])
def add_observacao(pedido_numero):
    try:
        data = request.get_json()
        nova_obs = data.get('observacao')
        if not nova_obs:
            return jsonify({"error": "Observação é obrigatória"}), 400

        # Busca o pedido atual para verificar as colunas obs
        response = supabase.table('pedidos_finalizados').select('obs2, obs3, obs4').eq('pedido_numero', pedido_numero).execute()
        if not response.data:
            return jsonify({"error": "Pedido não encontrado"}), 404

        pedido = response.data[0]
        update_data = {}

        if not pedido.get('obs2'):
            update_data['obs2'] = nova_obs
        elif not pedido.get('obs3'):
            update_data['obs3'] = nova_obs
        elif not pedido.get('obs4'):
            update_data['obs4'] = nova_obs
        else:
            return jsonify({"error": "Limite de observações adicionais atingido"}), 400

        # Atualiza o pedido
        supabase.table('pedidos_finalizados').update(update_data).eq('pedido_numero', pedido_numero).execute()
        return jsonify({"message": "Observação adicionada com sucesso"}), 200

    except Exception as e:
        logging.error(f"Erro ao adicionar observação: {str(e)}")
        return jsonify({"error": "Erro interno no servidor"}), 500

# Rota /pedidos/lele_data (pra simulação, substitua por /pedidos/lele depois)
@app.route('/pedidos/lele_data', methods=['GET'])
def pedidos_lele_data():
    response = supabase.table('pedidos_finalizados').select('*').order('pedido_numero', desc=True).execute()
    pedidos = response.data or []
    for p in pedidos:
        if isinstance(p.get('produto'), str):
            p['produto'] = json.loads(p['produto']) if p['produto'] else []
    return jsonify(pedidos)
    
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
