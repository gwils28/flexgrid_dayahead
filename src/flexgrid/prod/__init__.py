"""Service J-1 (bloc D) : apprentissage hebdomadaire versionné, prévision quotidienne, nomination, API.

Mode « rejeu » : le service tourne sur les snapshots figés, pour une date d'émission passée. Les entrées sont
coupées à l'horloge de nomination exactement comme dans le backtest ; brancher les API temps réel ne change que
l'ingestion.
"""
