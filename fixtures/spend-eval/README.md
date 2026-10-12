# resumidor

Servicio que resume contratos para el equipo comercial. El prompt vive en
`prompts/summarize.txt`; el código que lo llama no cambia entre versiones.

## Evals

`evals/run.py` corre los 400 documentos de `evals/dataset.jsonl` contra el
modelo de producción y compara con las referencias. Una corrida completa
cuesta unos **USD 8** y se factura al presupuesto mensual del equipo de
datos (USD 120 por mes). No hay modo barato: cada documento es una llamada.
