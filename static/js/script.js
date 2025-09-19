var carrinho = carrinho || [];

document.addEventListener('DOMContentLoaded', () => {
    // Exibe a categoria padrão ao carregar
    showCategoria('Bebidas quentes e batidas');
});

function showCategoria(categoria) {
    document.querySelectorAll('.categoria').forEach(div => div.style.display = 'none');
    document.getElementById(categoria).style.display = 'block';
}

function adicionarAoCarrinho(id, preco, nome, categoria) {
    let sabor = '';
    if (categoria === 'PÃO COM CHURRAS') {
        const select = document.getElementById(`sabor-${nome}`);
        sabor = select ? select.value : '';
    }
    carrinho.push({ id, preco: parseFloat(preco), nome, sabor });
    atualizarCarrinho();
    abrirCarrinhoPopup();
}

function atualizarCarrinho() {
    const total = carrinho.reduce((soma, item) => soma + item.preco, 0);
    document.getElementById('carrinho-info').textContent = `Itens: ${carrinho.length} | Total: R$ ${total.toFixed(2)}`;
    const itensDiv = document.getElementById('carrinhoItens');
    if (itensDiv) {
        itensDiv.innerHTML = carrinho.map(item => `
            <div style="display:flex; justify-content:space-between; margin:5px 0;">
                <span>${item.nome} (${item.sabor || 'Sem sabor'}) - R$ ${item.preco.toFixed(2)}</span>
                <button onclick="removerDoCarrinho('${item.id}')" style="color:#8B0000; background:none; border:none; cursor:pointer;">X</button>
            </div>
        `).join('');
    }
}

function removerDoCarrinho(id) {
    carrinho = carrinho.filter(item => item.id !== id);
    atualizarCarrinho();
}

function abrirCarrinhoPopup() {
    document.getElementById('carrinhoPopup').style.display = 'flex';
    atualizarCarrinho();
}

function fecharCarrinhoPopup() {
    document.getElementById('carrinhoPopup').style.display = 'none';
}

function abrirModal() {
    document.getElementById('modal').style.display = 'flex';
}

function fecharModal() {
    document.getElementById('modal').style.display = 'none';
}

async function enviarPedido() {
    const mesa = document.getElementById('mesa').value.trim();
    const contato = document.getElementById('contato').value.trim();
    const obs = document.getElementById('obs').value || '';

    if (carrinho.length === 0) {
        alert("Adicione itens ao pedido antes de finalizar!");
        return;
    }
    if (!mesa || !contato) {
        alert("Mesa e contato são obrigatórios!");
        return;
    }

    const total = carrinho.reduce((sum, item) => sum + item.preco, 0);
    const pedido = {
        mesa,
        contato,
        observacoes: obs,
        produto: carrinho.map(item => ({
            id: item.id,
            quantidade: 1,
            observacao: obs,
            sabor: item.sabor
        })),
        total
    };

    try {
        document.querySelector('#modal button[onclick="enviarPedido()"]').innerHTML = '<div class="spinner"></div> Enviando...';
        const response = await fetch('/enviar_pedido', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(pedido),
        });

        if (!response.ok) {
            const text = await response.text();
            throw new Error(`Erro ${response.status}: ${text}`);
        }

        const data = await response.json();
        alert(data.message);
        window.location.href = '/pedidos/meuspedidos';
        carrinho = [];
        atualizarCarrinho();
        fecharModal();
    } catch (error) {
        alert('Erro ao processar o pedido: ' + error.message);
        console.error('Erro:', error);
    } finally {
        document.querySelector('#modal button[onclick="enviarPedido()"]').innerHTML = 'Enviar Pedido';
    }
}
