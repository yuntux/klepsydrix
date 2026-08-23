# Voix de référence F5-TTS

Extrait de voix utilisé par `generate_demo.py` pour le clonage vocal (F5-TTS).

- **Source** : LibriVox, *Candide ou l'Optimisme* (Voltaire), chapitre 29, lu par **Bernard**.
  https://librivox.org/notre-dame-de-paris-by-victor-hugo/ (catalogue) —
  fichier d'origine : https://www.archive.org/download/candide_ou_loptimisme_b_librivox/candide_29_voltaire_64kb.mp3
- **Licence** : domaine public (tous les enregistrements LibriVox le sont).
- **Traitement** : décalage de 2s (annonce), débruitage léger (`noisereduce`, `prop_decrease=0.6`),
  suppression des silences (`librosa.effects.trim`, `top_db=30`), tronqué à 10s, normalisé à -1dB.
- **Voix vérifiée masculine** : F0 moyenne 112,4 Hz / médiane 113,9 Hz (plage homme adulte
  typique : 85-180 Hz), mesurée via `librosa.pyin`.
- `bernard_ref.txt` : transcription (Whisper `base`, langue forcée `fr`) utilisée comme `ref_text`
  F5-TTS — le contenu exact n'a aucune importance (jamais reproduit dans la sortie), seul le style
  vocal compte.

⚠️ Le checkpoint utilisé pour la synthèse (`RASPIAUDIO/F5-French-MixedSpeakers-reduced`) est sous
licence **CC-BY-NC-4.0 (non-commercial)** — voir `generate_demo.py`. Cette voix de référence
(LibriVox, domaine public) n'a pas cette restriction ; c'est le *checkpoint* qui limite l'usage.
