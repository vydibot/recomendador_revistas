# Scripts

Puntos de entrada operativos para ejecutar el pipeline, entrenar modelos y
generar evaluaciones. Todos los scripts operativos viven dentro de este
paquete.

Puntos de entrada disponibles:

- `run_pipeline.py`: Bronze -> Silver -> Gold.
- `report_apc.py`: reporte de calidad APC.

Los futuros comandos de entrenamiento y evaluación se incorporarán aquí:

- `train_tfidf.py`: ajuste del modelo TF-IDF.
- `train_scibert.py`: generación de embeddings SciBERT.
- `evaluate_models.py`: evaluación comparativa.