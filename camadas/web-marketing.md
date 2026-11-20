# Camada: web e marketing

Para sistemas que geram conteúdo e publicam em canais externos (site, redes sociais).

**Risco dominante:** publicar em público algo errado ou exposto. Publicar é irreversível na prática.
Um rascunho que cita cliente, sócio, IP, domínio interno ou configuração é vazamento, mesmo com o
código perfeito.

## O planejador pergunta
- De que fonte vem o conteúdo, e ela está na lista de fontes permitidas?
- Envolve terceiro (sócio, cliente)? Qual canal, e qual o limite de tamanho e formato dele?
- A mudança cria ou altera alguma rota que publica? (Se sim, é classe A.)

## O revisor procura
- Rota de publicação que não passa pelo registro de aprovação.
- Credencial de rede social em código, log, fixture ou mensagem de erro.
- Termo proibido que escapa do filtro (maiúsculas, acento, partido em duas linhas, dentro de URL).
- Link quebrado, texto acima do limite do canal.

## A CI roda, além do núcleo
- Filtro de termos proibidos sobre todo rascunho dos testes.
- Teste que prova que nenhuma publicação acontece sem registro de aprovação.
- Limite de tamanho por canal; build do site e checagem de links.

## Regras fixas
- Nada é publicado sem aprovação registrada (quem, quando, qual versão do texto). Em nenhuma fase.
- Credenciais de rede social ficam só no serviço de publicação, nunca no ambiente do agente que escreve código.
- Fontes de conteúdo são lidas, nunca escritas.
- Texto gerado é produto: é avaliado por amostra (nota de 1 a 5 do responsável pelo projeto), com métrica separada da fábrica.
