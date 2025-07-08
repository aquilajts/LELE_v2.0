import sqlite3

conn = sqlite3.connect('vendas.db')
cur = conn.cursor()

cur.execute('''
CREATE TABLE IF NOT EXISTS vendas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT,
    cliente TEXT,
    telefone TEXT,
    veiculo TEXT,
    placa TEXT,
    fipe TEXT,
    mensalidade_original TEXT,
    mensalidade_desconto TEXT,
    participacao TEXT,
    desconto TEXT,
    observacoes TEXT,
    usuario_id TEXT
)
''')

conn.commit()
conn.close()

print("Banco de dados e tabela 'vendas' criados com sucesso.")
