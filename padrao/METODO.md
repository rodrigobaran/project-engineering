# Método de trabalho do agente

1. **Antes de editar:** localizar o ponto de entrada, a implementação atual e os testes. Escrever em uma
   frase o resultado observável e o comportamento que precisa ser preservado.
2. **Durante:** reaproveitar o que já resolve. Cada arquivo alterado contribui para o aceite.
   Refatoração paralela vai para outro PR.
3. **Antes de entregar:** reler o diff como revisor. Procurar código morto, parâmetro sem uso, abstração
   sem necessidade, tratamento de erro que esconde falha e teste que passa com o comportamento quebrado.
   Rodar `verificar` e `testar` e registrar o resultado real no PR.
4. **Revisão independente:** o revisor recebe tarefa, critério de aceite, diff e log da CI. Cada achado
   aponta arquivo, entrada que quebra e consequência. Achado sem cenário concreto não bloqueia.

Proibido ao agente: editar `.fabrica/` (muda-se na fábrica), remover asserção ou teste sem dizer por quê
no PR, publicar ou enviar qualquer coisa para fora do repositório.
