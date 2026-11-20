# Instruções para agentes: a fábrica

Este repositório é o portão dos outros: mudança aqui é sempre classe A e precisa do ok do Rodrigo.

## Regra master: autoria

- Nenhum agente aparece como autor ou coautor de commit: sem `Co-Authored-By`, sem linha de sessão,
  sem identidade de agente no autor ou no committer. O autor é o Rodrigo.
- Quem escreveu o quê (qual agente, qual modelo) fica registrado na descrição do PR, não no commit.

## Como mudar

- Proponha antes: o conteúdo do commit, a mensagem e as alternativas consideradas. Nada vai para o
  GitHub sem o ok do Rodrigo para aquele commit.
- Classe A e tudo que pede ADR: mostre o que pretende fazer e as outras opções antes de escrever código.
- Sem dependências de execução: só biblioteca padrão do Python 3.11+. Dependência nova exige ADR.
- Mudança em `padrao/`, `camadas/` ou `papeis/` muda o comportamento de todos os projetos na próxima
  sincronização. Diga no PR quais projetos isso afeta.
- Decisões em `docs/decisoes/`.

As regras para o software que a fábrica cria são outras e ficam em `padrao/`, quando esse commit entrar.
