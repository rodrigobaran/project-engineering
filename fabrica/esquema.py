"""Validação de JSON Schema num subconjunto pequeno, só com a biblioteca padrão.

Os schemas da fábrica (`papeis/schemas/`, `descoberta/schema.json`) usam só as palavras abaixo. Uma palavra
fora da lista é erro do schema, não algo a ignorar: um validador que pula o que não entende deixa passar
justamente o que o schema queria barrar.

Suportadas: type, enum, const, required, properties, additionalProperties (booleano), items, minItems,
minLength, pattern, $ref para `#/$defs/...`. Anotações ignoradas: $schema, $id, $defs, title, description.
"""
from __future__ import annotations

import re
from typing import Any

SUPORTADAS = {"type", "enum", "const", "required", "properties", "additionalProperties", "items", "minItems",
              "minLength", "pattern", "$ref"}
ANOTACOES = {"$schema", "$id", "$defs", "title", "description"}
_TIPOS = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


class ErroSchema(ValueError):
    pass


def _tipo_confere(valor: Any, tipo: str) -> bool:
    if tipo == "integer":
        return isinstance(valor, int) and not isinstance(valor, bool)
    if tipo == "number":
        return isinstance(valor, int | float) and not isinstance(valor, bool)
    if tipo not in _TIPOS:
        raise ErroSchema(f"tipo desconhecido no schema: {tipo!r}")
    return isinstance(valor, _TIPOS[tipo])


def _resolver(ref: str, raiz: dict) -> dict:
    if not ref.startswith("#/$defs/"):
        raise ErroSchema(f"só $ref local para #/$defs/ é suportado: {ref!r}")
    nome = ref.removeprefix("#/$defs/")
    try:
        return raiz["$defs"][nome]
    except KeyError as e:
        raise ErroSchema(f"$ref não encontrado: {ref!r}") from e


def validar(valor: Any, schema: dict, raiz: dict | None = None, caminho: str = "$") -> list[str]:
    """Devolve a lista de erros, cada um com o caminho do valor (vazia quando o valor é válido)."""
    raiz = schema if raiz is None else raiz
    desconhecidas = set(schema) - SUPORTADAS - ANOTACOES
    if desconhecidas:
        raise ErroSchema(f"palavras não suportadas em {caminho}: {sorted(desconhecidas)}")
    if "$ref" in schema:
        return validar(valor, _resolver(schema["$ref"], raiz), raiz, caminho)

    erros: list[str] = []
    if "type" in schema:
        tipos = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_tipo_confere(valor, t) for t in tipos):
            return [f"{caminho}: esperava {' ou '.join(tipos)}, veio {type(valor).__name__}"]
    if "const" in schema and valor != schema["const"]:
        erros.append(f"{caminho}: precisa ser {schema['const']!r}")
    if "enum" in schema and valor not in schema["enum"]:
        erros.append(f"{caminho}: {valor!r} fora de {schema['enum']}")
    if isinstance(valor, str):
        if len(valor) < schema.get("minLength", 0):
            erros.append(f"{caminho}: texto com menos de {schema['minLength']} caractere(s)")
        if "pattern" in schema and re.search(schema["pattern"], valor) is None:
            erros.append(f"{caminho}: {valor!r} não casa {schema['pattern']!r}")
    if isinstance(valor, list):
        if len(valor) < schema.get("minItems", 0):
            erros.append(f"{caminho}: lista com menos de {schema['minItems']} item(ns)")
        if "items" in schema:
            for i, item in enumerate(valor):
                erros.extend(validar(item, schema["items"], raiz, f"{caminho}[{i}]"))
    if isinstance(valor, dict):
        for chave in schema.get("required", []):
            if chave not in valor:
                erros.append(f"{caminho}: falta '{chave}'")
        propriedades = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        if not isinstance(extra, bool):
            raise ErroSchema(f"{caminho}: additionalProperties só aceita booleano aqui")
        for chave, sub in valor.items():
            if chave in propriedades:
                erros.extend(validar(sub, propriedades[chave], raiz, f"{caminho}.{chave}"))
            elif not extra:
                erros.append(f"{caminho}: campo não previsto '{chave}'")
    return erros


def conferir_schema(schema: dict, caminho: str = "#") -> None:
    """Percorre o schema inteiro e falha na primeira palavra fora do subconjunto suportado."""
    desconhecidas = set(schema) - SUPORTADAS - ANOTACOES
    if desconhecidas:
        raise ErroSchema(f"palavras não suportadas em {caminho}: {sorted(desconhecidas)}")
    for nome, sub in schema.get("properties", {}).items():
        conferir_schema(sub, f"{caminho}/properties/{nome}")
    for nome, sub in schema.get("$defs", {}).items():
        conferir_schema(sub, f"{caminho}/$defs/{nome}")
    if isinstance(schema.get("items"), dict):
        conferir_schema(schema["items"], f"{caminho}/items")
