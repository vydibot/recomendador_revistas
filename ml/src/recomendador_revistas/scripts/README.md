# Scripts

Puntos de entrada operativos para ejecutar el pipeline, entrenar modelos y
generar evaluaciones. Todos los scripts operativos viven dentro de este
paquete.

Puntos de entrada disponibles:

- `run_pipeline.py`: Bronze -> Silver -> Gold.
- `report_apc.py`: reporte de calidad APC.
- `train_thematic_profile.py`: entrenamiento TF-IDF + SciBERT del Módulo A.
- `evaluate_journal.py`: similitud de una revista contra el resto del Gold.
- `evaluate_manuscript.py`: compara título, resumen y palabras clave contra el Gold.
- `evaluate_models.py`: split 80/20 de manuscritos, validación interna sin fuga para `alpha` y evaluación Top-N (TF-IDF, SciBERT, fusión).

Los futuros comandos de entrenamiento y evaluación se incorporarán aquí:

- `train_tfidf.py`: ajuste del modelo TF-IDF.
- `train_scibert.py`: generación de embeddings SciBERT.
- `evaluate_models.py`: evaluación comparativa.

La ejecución recomendada de la evaluación es:

```bash
.venv/bin/python src/recomendador_revistas/scripts/evaluate_models.py \
	--evaluation-csv src/recomendador_revistas/data/gold/articulos_tokens.csv \
	--seed 42 --test-size 0.2 \
	--alpha-grid 0.0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0 \
	--output-json src/recomendador_revistas/reports/model_eval_topn.json
```